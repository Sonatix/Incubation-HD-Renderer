// HD texture injection for OpenGlide: replace a 256x256 RGB565 with a bigger RGBA
// from hd_pack_hd/<fnv8hex>.rgba  (header: uint32 width, uint32 height, then RGBA8 rows).
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>

// GL constants not in the ancient <GL/gl.h> (GL 1.1). All usable through the
// core glTexParameter* entry points, so no wglGetProcAddress needed.
#ifndef GL_GENERATE_MIPMAP
#define GL_GENERATE_MIPMAP                 0x8191   // auto-build mip chain on glTexImage2D
#endif
#ifndef GL_LINEAR_MIPMAP_LINEAR
#define GL_LINEAR_MIPMAP_LINEAR            0x2703   // trilinear
#endif
#ifndef GL_TEXTURE_MAX_ANISOTROPY_EXT
#define GL_TEXTURE_MAX_ANISOTROPY_EXT      0x84FE
#define GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT  0x84FF
#endif

static unsigned incu_fnv(const unsigned char *p, unsigned n) {
    unsigned h = 2166136261u;
    for (unsigned i = 0; i < n; i++) { h ^= p[i]; h *= 16777619u; }
    return h;
}

// Trilinear + anisotropic filtering for HD textures. The base texture params were
// set by PGTexture before try_hd_replace runs, so overriding them here is final.
// GL_GENERATE_MIPMAP must be set BEFORE glTexImage2D to auto-build the mip chain.
static void hd_enable_mipmaps_pre(void) {
    glTexParameteri(GL_TEXTURE_2D, GL_GENERATE_MIPMAP, GL_TRUE);
}
static void hd_set_filtering_post(void) {
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    static float maxAniso = -1.0f;
    if (maxAniso < 0.0f) {
        maxAniso = 0.0f;
        glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT, &maxAniso);
    }
    if (maxAniso > 1.0f) {
        float a = maxAniso < 16.0f ? maxAniso : 16.0f;
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT, a);
    }
}

bool try_hd_replace(const void *data, unsigned w, unsigned h) {
    if (!data || w != 256 || h != 256) return false;
    unsigned fnv = incu_fnv((const unsigned char *)data, w * h * 2);

    char path[128];
    sprintf(path, "hd_pack_hd\\%08x.rgba", fnv);

    FILE *lg = fopen("hd_inject.log", "at");
    if (lg) { fprintf(lg, "try %ux%u fnv=%08x\n", w, h, fnv); fclose(lg); }

    FILE *f = fopen(path, "rb");
    if (!f) return false;
    unsigned hd[2] = {0, 0};
    if (fread(hd, 4, 2, f) != 2 || !hd[0] || hd[0] > 4096) { fclose(f); return false; }
    unsigned nn = hd[0] * hd[1] * 4;
    void *buf = malloc(nn);
    size_t got = fread(buf, 1, nn, f);
    fclose(f);
    if (got == nn) {
        hd_enable_mipmaps_pre();
        glTexImage2D(GL_TEXTURE_2D, 0, 4, hd[0], hd[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, buf);
        hd_set_filtering_post();
        extern void bump3d_register(unsigned);   // experimental fake bump (bump3d.cpp)
        bump3d_register(fnv);
        FILE *l2 = fopen("hd_inject.log", "at");
        if (l2) { fprintf(l2, "  HIT %ux%u\n", hd[0], hd[1]); fclose(l2); }
    }
    free(buf);
    return got == nn;
}
