//**************************************************************
//* bump3d.cpp - EXPERIMENTAL fake bump/normal mapping for ONE 3D texture.
//*
//* At the Glide layer we get screen-space triangles with baked per-vertex
//* lighting and NO surface normals. So this is a *screen-space* fake: perturb a
//* forward-facing normal with an authored normal map and light it from a fixed
//* direction, keeping flat areas unchanged (relief only, no overall tint). It
//* enriches the surface of the flat model faces; it does NOT change the low-poly
//* silhouette. Gated to the target FNV texture (soldiers) so nothing else is
//* touched. Toggle/strength via env INCU_BUMP (default 1.0; 0 = off).
//**************************************************************
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef GL_FRAGMENT_SHADER
#define GL_VERTEX_SHADER   0x8B31
#define GL_FRAGMENT_SHADER 0x8B30
#define GL_COMPILE_STATUS  0x8B81
#define GL_LINK_STATUS     0x8B82
#endif
#ifndef GL_TEXTURE0
#define GL_TEXTURE0 0x84C0
#define GL_TEXTURE1 0x84C1
#endif
typedef char GLchar;

typedef GLuint (WINAPI *P_CS)(GLenum);
typedef void   (WINAPI *P_SS)(GLuint,GLsizei,const GLchar* const*,const GLint*);
typedef void   (WINAPI *P_C)(GLuint);
typedef void   (WINAPI *P_GSIV)(GLuint,GLenum,GLint*);
typedef void   (WINAPI *P_GSIL)(GLuint,GLsizei,GLsizei*,GLchar*);
typedef GLuint (WINAPI *P_CP)(void);
typedef void   (WINAPI *P_AS)(GLuint,GLuint);
typedef void   (WINAPI *P_LP)(GLuint);
typedef void   (WINAPI *P_GPIV)(GLuint,GLenum,GLint*);
typedef void   (WINAPI *P_UP)(GLuint);
typedef GLint  (WINAPI *P_GUL)(GLuint,const GLchar*);
typedef void   (WINAPI *P_U1I)(GLint,GLint);
typedef void   (WINAPI *P_U1F)(GLint,GLfloat);
typedef void   (WINAPI *P_U3F)(GLint,GLfloat,GLfloat,GLfloat);
typedef void   (WINAPI *P_AT)(GLenum);

static P_CS pCreateShader; static P_SS pShaderSource; static P_C pCompileShader;
static P_GSIV pGetShaderiv; static P_GSIL pGetShaderInfoLog; static P_CP pCreateProgram;
static P_AS pAttachShader; static P_LP pLinkProgram; static P_GPIV pGetProgramiv;
static P_UP pUseProgram; static P_GUL pGetUniformLocation; static P_U1I pUniform1i;
static P_U1F pUniform1f; static P_U3F pUniform3f; static P_AT pActiveTexture;

static bool   g_triedFuncs = false, g_haveFuncs = false, g_triedProg = false, g_haveProg = false;
static GLuint g_prog = 0;

// Per-fnv normal-texture cache: each HD texture with a <fnv>_n.rgba gets its
// normal map loaded once (0 = looked up, no normal map -> no bump).
static unsigned g_fnv[256]; static GLuint g_norm[256]; static int g_nCache = 0;

// The game re-uploads textures constantly, each time with a NEW GL id, so we
// map every bound base-texture id -> its normal texture (0 = no bump).
struct BumpMap { GLuint base; GLuint normal; };
static BumpMap g_map[1024]; static int g_mapCount = 0;
static GLint  g_uBase = -1, g_uNorm = -1, g_uLight = -1, g_uStrength = -1;
static float  g_strength = 1.0f;
static bool   g_enabled = true;

static const char *VS =
    "void main(){ gl_Position=ftransform(); gl_TexCoord[0]=gl_MultiTexCoord0; gl_FrontColor=gl_Color; }";
static const char *FS =
    "uniform sampler2D baseTex; uniform sampler2D normalTex;\n"
    "uniform vec3 lightDir; uniform float strength;\n"
    "void main(){\n"
    "  vec4 base = texture2DProj(baseTex, gl_TexCoord[0]);\n"
    "  vec4 nmt = texture2DProj(normalTex, gl_TexCoord[0]);\n"
    "  if (strength > 10.0) { gl_FragColor = vec4(nmt.rgb, base.a); return; }\n"  // diag: show normals
    "  vec3 N = normalize(nmt.rgb*2.0-1.0);\n"
    "  vec3 L = normalize(lightDir);\n"
    "  float lit = 1.0 + strength*(dot(N,L) - L.z);\n"   // flat (N=z) => lit=1
    "  lit = clamp(lit, 0.0, 2.0);\n"
    "  gl_FragColor = vec4(base.rgb*gl_Color.rgb*lit, base.a*gl_Color.a);\n"
    "}";

#define GET(v,t,n) v=(t)wglGetProcAddress(n); if(!v) return false;
static bool loadFuncs(){
    GET(pCreateShader,P_CS,"glCreateShader"); GET(pShaderSource,P_SS,"glShaderSource");
    GET(pCompileShader,P_C,"glCompileShader"); GET(pGetShaderiv,P_GSIV,"glGetShaderiv");
    GET(pGetShaderInfoLog,P_GSIL,"glGetShaderInfoLog"); GET(pCreateProgram,P_CP,"glCreateProgram");
    GET(pAttachShader,P_AS,"glAttachShader"); GET(pLinkProgram,P_LP,"glLinkProgram");
    GET(pGetProgramiv,P_GPIV,"glGetProgramiv"); GET(pUseProgram,P_UP,"glUseProgram");
    GET(pGetUniformLocation,P_GUL,"glGetUniformLocation"); GET(pUniform1i,P_U1I,"glUniform1i");
    GET(pUniform1f,P_U1F,"glUniform1f"); GET(pUniform3f,P_U3F,"glUniform3f");
    GET(pActiveTexture,P_AT,"glActiveTexture");
    return true;
}
static GLuint comp(GLenum t,const char*s){
    GLuint sh=pCreateShader(t); pShaderSource(sh,1,&s,NULL); pCompileShader(sh);
    GLint ok=0; pGetShaderiv(sh,GL_COMPILE_STATUS,&ok);
    if(!ok){ char log[512]; pGetShaderInfoLog(sh,sizeof(log),NULL,log);
        FILE*f=fopen("OpenGLid.log","at"); if(f){fprintf(f,"bump3d compile fail: %s\n",log);fclose(f);} return 0; }
    return sh;
}
static void buildProg(){
    g_triedProg=true;
    const char*e=getenv("INCU_BUMP"); if(e) g_strength=(float)atof(e);
    if(g_strength<=0.0f){ g_enabled=false; return; }
    if(!g_haveFuncs) return;
    GLuint vs=comp(GL_VERTEX_SHADER,VS), fs=comp(GL_FRAGMENT_SHADER,FS);
    if(!vs||!fs) return;
    g_prog=pCreateProgram(); pAttachShader(g_prog,vs); pAttachShader(g_prog,fs); pLinkProgram(g_prog);
    GLint ok=0; pGetProgramiv(g_prog,GL_LINK_STATUS,&ok); if(!ok) return;
    g_uBase=pGetUniformLocation(g_prog,"baseTex"); g_uNorm=pGetUniformLocation(g_prog,"normalTex");
    g_uLight=pGetUniformLocation(g_prog,"lightDir"); g_uStrength=pGetUniformLocation(g_prog,"strength");
    g_haveProg=true;
    FILE*f=fopen("OpenGLid.log","at"); if(f){fprintf(f,"bump3d ready (strength=%.2f)\n",g_strength);fclose(f);}
}

// Load (once) the normal texture for an fnv, or 0 if it has no <fnv>_n.rgba.
static GLuint normal_for_fnv(unsigned fnv, GLuint restoreBinding){
    for(int i=0;i<g_nCache;i++) if(g_fnv[i]==fnv) return g_norm[i];   // cached (may be 0)
    GLuint nt=0;
    char path[128]; sprintf(path,"hd_pack_hd\\%08x_n.rgba",fnv);
    FILE*fp=fopen(path,"rb");
    if(fp){
        unsigned hd[2]={0,0};
        if(fread(hd,4,2,fp)==2 && hd[0] && hd[0]<=4096){
            unsigned n=hd[0]*hd[1]*4; void*buf=malloc(n);
            if(fread(buf,1,n,fp)==n){
                glGenTextures(1,&nt); glBindTexture(GL_TEXTURE_2D,nt);
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
                glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
                glTexImage2D(GL_TEXTURE_2D,0,4,hd[0],hd[1],0,GL_RGBA,GL_UNSIGNED_BYTE,buf);
                glBindTexture(GL_TEXTURE_2D,restoreBinding);
            }
            free(buf);
        }
        fclose(fp);
    }
    if(g_nCache<256){ g_fnv[g_nCache]=fnv; g_norm[g_nCache]=nt; g_nCache++; }
    return nt;
}

// Called from hd_inject after every HD texture is uploaded (and bound). Maps the
// bound GL id to its normal texture, or clears the mapping if it has none (so a
// reused GL id doesn't keep a stale bump).
void bump3d_register(unsigned fnv){
    if(!g_triedFuncs){ g_triedFuncs=true; g_haveFuncs=loadFuncs(); }
    if(!g_haveFuncs) return;
    GLint prev=0; glGetIntegerv(GL_TEXTURE_BINDING_2D,&prev);
    GLuint normal = normal_for_fnv(fnv,(GLuint)prev);

    int slot=-1;
    for(int i=0;i<g_mapCount;i++) if(g_map[i].base==(GLuint)prev){ slot=i; break; }
    if(normal){
        if(slot<0 && g_mapCount<1024){ slot=g_mapCount++; g_map[slot].base=(GLuint)prev; }
        if(slot>=0) g_map[slot].normal=normal;
    } else if(slot>=0){
        g_map[slot].normal=0;   // this GL id no longer maps to a bumped texture
    }
}

// Called in RenderDrawTriangles just before the draw. Activates the bump shader
// only when the currently bound texture is our target. Returns true if active.
bool bump3d_begin(void){
    if(!g_triedProg) buildProg();
    if(!g_enabled || !g_haveProg || g_mapCount==0) return false;
    GLint cur=0; glGetIntegerv(GL_TEXTURE_BINDING_2D,&cur);
    GLuint normal=0;
    for(int i=0;i<g_mapCount;i++) if(g_map[i].base==(GLuint)cur){ normal=g_map[i].normal; break; }
    if(!normal) return false;
    pActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D,normal);
    pActiveTexture(GL_TEXTURE0);
    pUseProgram(g_prog);
    pUniform1i(g_uBase,0); pUniform1i(g_uNorm,1);
    pUniform3f(g_uLight,-0.6f,-0.6f,1.0f);
    pUniform1f(g_uStrength,g_strength);
    return true;
}
void bump3d_end(void){
    if(!g_haveProg) return;
    pUseProgram(0);
    pActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D,0);
    pActiveTexture(GL_TEXTURE0);
}
