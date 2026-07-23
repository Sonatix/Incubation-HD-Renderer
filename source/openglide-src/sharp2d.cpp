//**************************************************************
//* sharp2d.cpp - a small GLSL sharpening pass for the 2D (LFB) layer.
//*
//* The game composites its whole UI into a 640x480 image that we upload to
//* Glide.LFBTexture and stretch to the screen. Bilinear makes it smooth but
//* soft. This runs an unsharp-mask fragment shader while that quad is drawn,
//* so menus/briefings come out crisper. Fixed-function-friendly (GLSL 1.20,
//* uses ftransform / gl_TexCoord), and fails safe: if the shader can't be
//* built, sharp2d_begin returns false and the caller draws normally.
//*
//* Strength is tunable via env INCU_SHARP (0 = off, default 0.30).
//**************************************************************
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef GL_FRAGMENT_SHADER
#define GL_VERTEX_SHADER    0x8B31
#define GL_FRAGMENT_SHADER  0x8B30
#define GL_COMPILE_STATUS   0x8B81
#define GL_LINK_STATUS      0x8B82
#endif
typedef char GLchar;

typedef GLuint (WINAPI *PFN_CREATESHADER)(GLenum);
typedef void   (WINAPI *PFN_SHADERSOURCE)(GLuint, GLsizei, const GLchar* const*, const GLint*);
typedef void   (WINAPI *PFN_COMPILESHADER)(GLuint);
typedef void   (WINAPI *PFN_GETSHADERIV)(GLuint, GLenum, GLint*);
typedef void   (WINAPI *PFN_GETSHADERINFOLOG)(GLuint, GLsizei, GLsizei*, GLchar*);
typedef GLuint (WINAPI *PFN_CREATEPROGRAM)(void);
typedef void   (WINAPI *PFN_ATTACHSHADER)(GLuint, GLuint);
typedef void   (WINAPI *PFN_LINKPROGRAM)(GLuint);
typedef void   (WINAPI *PFN_GETPROGRAMIV)(GLuint, GLenum, GLint*);
typedef void   (WINAPI *PFN_USEPROGRAM)(GLuint);
typedef GLint  (WINAPI *PFN_GETUNIFORMLOCATION)(GLuint, const GLchar*);
typedef void   (WINAPI *PFN_UNIFORM1I)(GLint, GLint);
typedef void   (WINAPI *PFN_UNIFORM1F)(GLint, GLfloat);
typedef void   (WINAPI *PFN_UNIFORM2F)(GLint, GLfloat, GLfloat);

static PFN_CREATESHADER        p_CreateShader;
static PFN_SHADERSOURCE        p_ShaderSource;
static PFN_COMPILESHADER       p_CompileShader;
static PFN_GETSHADERIV         p_GetShaderiv;
static PFN_GETSHADERINFOLOG    p_GetShaderInfoLog;
static PFN_CREATEPROGRAM       p_CreateProgram;
static PFN_ATTACHSHADER        p_AttachShader;
static PFN_LINKPROGRAM         p_LinkProgram;
static PFN_GETPROGRAMIV        p_GetProgramiv;
static PFN_USEPROGRAM          p_UseProgram;
static PFN_GETUNIFORMLOCATION  p_GetUniformLocation;
static PFN_UNIFORM1I           p_Uniform1i;
static PFN_UNIFORM1F           p_Uniform1f;
static PFN_UNIFORM2F           p_Uniform2f;

static bool   g_tried = false, g_ok = false;
static GLuint g_prog = 0;
static GLint  g_uTex = -1, g_uTexel = -1, g_uAmount = -1;
static float  g_amount = 0.30f;

static const char *VS =
    "void main(){ gl_Position = ftransform(); gl_TexCoord[0] = gl_MultiTexCoord0; }";

static const char *FS =
    "uniform sampler2D tex; uniform vec2 texel; uniform float amount;\n"
    "void main(){\n"
    "  vec2 uv = gl_TexCoord[0].xy;\n"
    "  vec4 c  = texture2D(tex, uv);\n"
    "  vec3 n  = texture2D(tex, uv+vec2(0.0,-texel.y)).rgb\n"
    "          + texture2D(tex, uv+vec2(0.0, texel.y)).rgb\n"
    "          + texture2D(tex, uv+vec2(-texel.x,0.0)).rgb\n"
    "          + texture2D(tex, uv+vec2( texel.x,0.0)).rgb;\n"
    "  vec3 s  = c.rgb + amount*(4.0*c.rgb - n);\n"
    "  gl_FragColor = vec4(clamp(s,0.0,1.0), c.a);\n"
    "}";

#define LOAD(var,type,name) var=(type)wglGetProcAddress(name); if(!var) return false;

static bool load_funcs()
{
    LOAD(p_CreateShader,       PFN_CREATESHADER,       "glCreateShader");
    LOAD(p_ShaderSource,       PFN_SHADERSOURCE,       "glShaderSource");
    LOAD(p_CompileShader,      PFN_COMPILESHADER,      "glCompileShader");
    LOAD(p_GetShaderiv,        PFN_GETSHADERIV,        "glGetShaderiv");
    LOAD(p_GetShaderInfoLog,   PFN_GETSHADERINFOLOG,   "glGetShaderInfoLog");
    LOAD(p_CreateProgram,      PFN_CREATEPROGRAM,      "glCreateProgram");
    LOAD(p_AttachShader,       PFN_ATTACHSHADER,       "glAttachShader");
    LOAD(p_LinkProgram,        PFN_LINKPROGRAM,        "glLinkProgram");
    LOAD(p_GetProgramiv,       PFN_GETPROGRAMIV,       "glGetProgramiv");
    LOAD(p_UseProgram,         PFN_USEPROGRAM,         "glUseProgram");
    LOAD(p_GetUniformLocation, PFN_GETUNIFORMLOCATION, "glGetUniformLocation");
    LOAD(p_Uniform1i,          PFN_UNIFORM1I,          "glUniform1i");
    LOAD(p_Uniform1f,          PFN_UNIFORM1F,          "glUniform1f");
    LOAD(p_Uniform2f,          PFN_UNIFORM2F,          "glUniform2f");
    return true;
}

static GLuint compile(GLenum type, const char *src)
{
    GLuint s = p_CreateShader(type);
    p_ShaderSource(s, 1, &src, NULL);
    p_CompileShader(s);
    GLint ok = 0; p_GetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512]; p_GetShaderInfoLog(s, sizeof(log), NULL, log);
        FILE *f = fopen("OpenGLid.log", "at");
        if (f) { fprintf(f, "sharp2d shader compile failed: %s\n", log); fclose(f); }
        return 0;
    }
    return s;
}

static void build()
{
    g_tried = true;
    const char *env = getenv("INCU_SHARP");
    if (env) g_amount = (float)atof(env);
    if (g_amount <= 0.0f) return;                 // disabled by user
    if (!load_funcs()) return;

    GLuint vs = compile(GL_VERTEX_SHADER, VS);
    GLuint fs = compile(GL_FRAGMENT_SHADER, FS);
    if (!vs || !fs) return;
    g_prog = p_CreateProgram();
    p_AttachShader(g_prog, vs);
    p_AttachShader(g_prog, fs);
    p_LinkProgram(g_prog);
    GLint ok = 0; p_GetProgramiv(g_prog, GL_LINK_STATUS, &ok);
    if (!ok) return;
    g_uTex    = p_GetUniformLocation(g_prog, "tex");
    g_uTexel  = p_GetUniformLocation(g_prog, "texel");
    g_uAmount = p_GetUniformLocation(g_prog, "amount");
    g_ok = true;
    FILE *f = fopen("OpenGLid.log", "at");
    if (f) { fprintf(f, "sharp2d ready (amount=%.2f)\n", g_amount); fclose(f); }
}

// Activate the sharpen program for the next quad. texSize = LFB texture size
// (texels). Returns false if unavailable -> caller draws with plain bilinear.
bool sharp2d_begin(int texSize)
{
    if (!g_tried) build();
    if (!g_ok) return false;
    p_UseProgram(g_prog);
    p_Uniform1i(g_uTex, 0);
    p_Uniform2f(g_uTexel, 1.0f / (float)texSize, 1.0f / (float)texSize);
    p_Uniform1f(g_uAmount, g_amount);
    return true;
}

void sharp2d_end(void)
{
    if (g_ok) p_UseProgram(0);
}
