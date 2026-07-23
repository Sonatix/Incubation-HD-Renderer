//**************************************************************
//*            OpenGLide - Glide to OpenGL Wrapper
//*             http://openglide.sourceforge.net
//*
//*   Windows specific functions for handling display window
//*
//*         OpenGLide is OpenSource under LGPL license
//*              Originaly made by Fabio Barros
//*      Modified by Paul for Glidos (http://www.glidos.net)
//*               Linux version by Simon White
//**************************************************************
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#if !defined C_USE_SDL && defined WIN32

#include <windows.h>
#include <io.h>
#include <math.h>
#include <GL/gl.h>

#include "GlOgl.h"

#include "platform/window.h"

static HDC   hDC;
static HGLRC hRC;
static HWND  hWND;
static struct
{
    FxU16 red[ 256 ];
    FxU16 green[ 256 ];
    FxU16 blue[ 256 ];
} old_ramp;

static BOOL ramp_stored  = false;
static BOOL mode_changed = false;

void ApplyGameGamma( void );      // defined below; also called from input_remap.cpp
void RestoreDesktopGamma( void );

// ---- MSAA pixel-format selection -----------------------------------------
// SetPixelFormat can be called only ONCE per window, and the multisample format
// enumerator (wglChoosePixelFormatARB) itself needs a live GL context. So we
// spin up a throwaway window+context, query the entry point, and use it to pick
// a multisampled format for the real DC. Returns a pixel-format index, or 0.
#define WGL_DRAW_TO_WINDOW_ARB   0x2001
#define WGL_SUPPORT_OPENGL_ARB   0x2010
#define WGL_DOUBLE_BUFFER_ARB    0x2011
#define WGL_PIXEL_TYPE_ARB       0x2013
#define WGL_TYPE_RGBA_ARB        0x202B
#define WGL_ACCELERATION_ARB     0x2003
#define WGL_FULL_ACCELERATION_ARB 0x2027
#define WGL_COLOR_BITS_ARB       0x2014
#define WGL_DEPTH_BITS_ARB       0x2022
#define WGL_STENCIL_BITS_ARB     0x2023
#define WGL_SAMPLE_BUFFERS_ARB   0x2041
#define WGL_SAMPLES_ARB          0x2042
typedef BOOL (WINAPI *PFNWGLCHOOSEPIXELFORMATARB)( HDC, const int*, const FLOAT*, UINT, int*, UINT* );

static int g_MSAASamples = 0;   // samples actually granted (0 = plain, no MSAA)

static int ChooseMSAAFormat( HDC realDC, int wantSamples )
{
    WNDCLASSA wc;
    ZeroMemory( &wc, sizeof( wc ) );
    wc.lpfnWndProc   = DefWindowProcA;
    wc.hInstance     = GetModuleHandleA( NULL );
    wc.lpszClassName = "OGLideMSAAProbe";
    RegisterClassA( &wc );

    HWND dummy = CreateWindowA( wc.lpszClassName, "", WS_OVERLAPPED,
                               0, 0, 8, 8, NULL, NULL, wc.hInstance, NULL );
    if ( !dummy ) return 0;
    HDC  ddc = GetDC( dummy );

    PIXELFORMATDESCRIPTOR pfd;
    ZeroMemory( &pfd, sizeof( pfd ) );
    pfd.nSize      = sizeof( pfd );
    pfd.nVersion   = 1;
    pfd.dwFlags    = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;
    int  bpf = ChoosePixelFormat( ddc, &pfd );
    SetPixelFormat( ddc, bpf, &pfd );
    HGLRC rc = wglCreateContext( ddc );
    wglMakeCurrent( ddc, rc );

    PFNWGLCHOOSEPIXELFORMATARB wglChoosePixelFormatARB =
        (PFNWGLCHOOSEPIXELFORMATARB)wglGetProcAddress( "wglChoosePixelFormatARB" );

    int chosen = 0;
    if ( wglChoosePixelFormatARB )
    {
        for ( int s = wantSamples; s >= 2 && !chosen; s >>= 1 )
        {
            int attribs[] = {
                WGL_DRAW_TO_WINDOW_ARB, TRUE,
                WGL_SUPPORT_OPENGL_ARB, TRUE,
                WGL_DOUBLE_BUFFER_ARB,  TRUE,
                WGL_PIXEL_TYPE_ARB,     WGL_TYPE_RGBA_ARB,
                WGL_ACCELERATION_ARB,   WGL_FULL_ACCELERATION_ARB,
                WGL_COLOR_BITS_ARB,     32,
                WGL_DEPTH_BITS_ARB,     24,
                WGL_STENCIL_BITS_ARB,   8,
                WGL_SAMPLE_BUFFERS_ARB, 1,
                WGL_SAMPLES_ARB,        s,
                0
            };
            UINT num = 0; int fmt = 0;
            if ( wglChoosePixelFormatARB( realDC, attribs, NULL, 1, &fmt, &num ) &&
                 num > 0 )
            {
                chosen = fmt;
                g_MSAASamples = s;
            }
        }
    }

    wglMakeCurrent( NULL, NULL );
    wglDeleteContext( rc );
    ReleaseDC( dummy, ddc );
    DestroyWindow( dummy );
    UnregisterClassA( wc.lpszClassName, wc.hInstance );
    return chosen;
}

bool InitialiseOpenGLWindow(FxU wnd, int x, int y, int width, int height)
{
    PIXELFORMATDESCRIPTOR   pfd;
    int                     PixFormat;
    unsigned int            BitsPerPixel;
    HWND                    hwnd = (HWND) wnd;

    if( hwnd == NULL )
    {
        hwnd = GetActiveWindow();
    }

    if ( hwnd == NULL )
    {
        MessageBox( NULL, "NULL window specified", "Error", MB_OK );
        exit( 1 );
    }

    mode_changed = false;

    if ( UserConfig.InitFullScreen )
    {
        SetWindowLong( hwnd, 
                       GWL_STYLE, 
                       WS_POPUP | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS );
        MoveWindow( hwnd, 0, 0, width, height, false );
        mode_changed = SetScreenMode( width, height );
    }
    else
    {
       RECT client;
       GetClientRect( hwnd, &client );
       // dgVoodoo's DDraw may have already made the game window screen-sized
       // (WindowedAttributes = fullscreensize). Adopt that size instead of
       // shrinking the window back to 640x480 - the scaling macros pillarbox
       // the 3D into the same 4:3 rect dgVoodoo uses for the 2D.
       if ( client.right - client.left > width &&
            client.bottom - client.top > height )
       {
           OpenGL.WindowWidth  = client.right - client.left;
           OpenGL.WindowHeight = client.bottom - client.top;
           GlideMsg( "Adopted existing window client %dx%d (Glide %dx%d)\n",
                     OpenGL.WindowWidth, OpenGL.WindowHeight, width, height );
           InstallInputRemap( hwnd );
       }
       else
       {
           RECT rect;
           rect.left = 0;
           rect.right = width;
           rect.top = 0;
           rect.bottom = height;

           AdjustWindowRectEx( &rect,
                               GetWindowLong( hwnd, GWL_STYLE ),
                               GetMenu( hwnd ) != NULL,
                               GetWindowLong( hwnd, GWL_EXSTYLE ) );
           MoveWindow( hwnd,
                       x, y,
                       x + ( rect.right - rect.left ),
                       y + ( rect.bottom - rect.top ),
                       true );
       }
    }

    hWND = hwnd;

    hDC = GetDC( hwnd );
    BitsPerPixel = GetDeviceCaps( hDC, BITSPIXEL );

    ZeroMemory( &pfd, sizeof( pfd ) );
    pfd.nSize        = sizeof( pfd );
    pfd.nVersion     = 1;
    pfd.dwFlags      = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType   = PFD_TYPE_RGBA;
    pfd.cColorBits   = BitsPerPixel;
    pfd.cDepthBits   = BitsPerPixel;

    // Prefer a multisampled format for hardware anti-aliasing of 3D polygon
    // edges. Falls back to the classic format if MSAA is unavailable. The 2D
    // menu (glDrawPixels) is unaffected - MSAA only smooths rasterized edges.
    PixFormat = ChooseMSAAFormat( hDC, 8 );
    if ( PixFormat )
    {
        GlideMsg( "MSAA pixel format %d, %dx samples\n", PixFormat, g_MSAASamples );
    }
    else if ( !( PixFormat = ChoosePixelFormat( hDC, &pfd ) ) )
    {
        MessageBox( NULL, "ChoosePixelFormat() failed:  "
                    "Cannot find a suitable pixel format.", "Error", MB_OK );
        exit( 1 );
    }

    // the window must have WS_CLIPCHILDREN and WS_CLIPSIBLINGS for this call to
    // work correctly, so we SHOULD set this attributes, not doing that yet
    if ( !SetPixelFormat( hDC, PixFormat, &pfd ) )
    {
        MessageBox( NULL, "SetPixelFormat() failed:  "
                    "Cannot set format specified.", "Error", MB_OK );
        exit( 1 );
    }

    DescribePixelFormat( hDC, PixFormat, sizeof( PIXELFORMATDESCRIPTOR ), &pfd );
    GlideMsg( "ColorBits	= %d\n", pfd.cColorBits );
    GlideMsg( "DepthBits	= %d\n", pfd.cDepthBits );

    if ( pfd.cDepthBits > 16 )
    {
        UserConfig.PrecisionFix = false;
    }

    hRC = wglCreateContext( hDC );
    wglMakeCurrent( hDC, hRC );

    if ( g_MSAASamples > 0 )
    {
        #ifndef GL_MULTISAMPLE
        #define GL_MULTISAMPLE 0x809D
        #endif
        glEnable( GL_MULTISAMPLE );
    }

    // Capture the desktop ramp so we can put it back. On HDR displays the app's
    // gamma boost must be undone whenever the game isn't the foreground window
    // (focus loss AND exit), or the desktop stays dark - see ApplyGameGamma /
    // RestoreDesktopGamma, driven from the input-remap WndProc + FinaliseWindow.
    HDC pDC = GetDC( NULL );
    ramp_stored = GetDeviceGammaRamp( pDC, &old_ramp );
    ReleaseDC( NULL, pDC );
    return true;
}

// Called once per grBufferSwap: if dgVoodoo resized the game window after
// grSstWinOpen (fullscreen kicks in late), adopt the new client size and
// re-apply the clip window so viewport/scissor/ortho pick up the new scale.
void CheckWindowResize( void )
{
    RECT client;

    if ( hWND == NULL || !GetClientRect( hWND, &client ) )
    {
        return;
    }

    int w = client.right - client.left;
    int h = client.bottom - client.top;

    if ( w <= 0 || h <= 0 ||
         ( w == (int)OpenGL.WindowWidth && h == (int)OpenGL.WindowHeight ) )
    {
        return;
    }

    OpenGL.WindowWidth  = w;
    OpenGL.WindowHeight = h;
    GlideMsg( "Window client resized to %dx%d - rescaling viewport\n", w, h );

    if ( w > (int)Glide.WindowWidth && h > (int)Glide.WindowHeight )
    {
        InstallInputRemap( hWND );
    }

    // black out the whole window once so the pillarbox bars are clean
    glDisable( GL_SCISSOR_TEST );
    glViewport( 0, 0, w, h );
    glClearColor( 0.0f, 0.0f, 0.0f, 1.0f );
    glClear( GL_COLOR_BUFFER_BIT );

    grClipWindow( Glide.State.ClipMinX, Glide.State.ClipMinY,
                  Glide.State.ClipMaxX, Glide.State.ClipMaxY );
}

void FinaliseOpenGLWindow( void)
{
    RemoveInputRemap( );
    RestoreDesktopGamma( );

    wglMakeCurrent( NULL, NULL );
    wglDeleteContext( hRC );
    ReleaseDC( hWND, hDC );

    if( mode_changed )
    {
        ResetScreenMode( );
    }
}

static float g_GameGamma = 1.0f;   // last value the game asked for (1.0 = none)

// Apply the game's gamma boost to the device ramp (the game relies on this to
// look right - without it the 3D is noticeably dark).
void ApplyGameGamma( void )
{
    if ( g_GameGamma <= 0.0f || g_GameGamma == 1.0f ) return;
    struct { WORD red[256], green[256], blue[256]; } ramp;
    for ( int i = 0; i < 256; i++ )
    {
        WORD v = (WORD)( 0xffff * pow( i / 255.0, 1.0 / g_GameGamma ) );
        ramp.red[i] = ramp.green[i] = ramp.blue[i] = v;
    }
    HDC pDC = GetDC( NULL );
    SetDeviceGammaRamp( pDC, &ramp );
    ReleaseDC( NULL, pDC );
}

// Put the desktop ramp back. Restore the captured ramp if we have it; otherwise
// a clean linear identity (the neutral state) so HDR desktops never stay dark.
void RestoreDesktopGamma( void )
{
    HDC pDC = GetDC( NULL );
    if ( ramp_stored )
    {
        SetDeviceGammaRamp( pDC, &old_ramp );
    }
    else
    {
        struct { WORD red[256], green[256], blue[256]; } id;
        for ( int i = 0; i < 256; i++ )
            id.red[i] = id.green[i] = id.blue[i] = (WORD)( i * 257 );
        SetDeviceGammaRamp( pDC, &id );
    }
    ReleaseDC( NULL, pDC );
}

void SetGamma(float value)
{
    g_GameGamma = value;
    ApplyGameGamma();
}

void RestoreGamma()
{
}

bool SetScreenMode(int &xsize, int &ysize)
{
    HDC     hdc;
    FxU32   bits_per_pixel;
    bool    found;
    DEVMODE DevMode;

    hdc = GetDC( hWND );
    bits_per_pixel = GetDeviceCaps( hdc, BITSPIXEL );
    ReleaseDC( hWND, hdc );
    
    found = false;
    DevMode.dmSize = sizeof( DEVMODE );
    
    for ( int i = 0; 
          !found && EnumDisplaySettings( NULL, i, &DevMode ) != false; 
          i++ )
    {
        if ( ( DevMode.dmPelsWidth == (FxU32)xsize ) && 
             ( DevMode.dmPelsHeight == (FxU32)ysize ) && 
             ( DevMode.dmBitsPerPel == bits_per_pixel ) )
        {
            found = true;
        }
    }
    
    return ( found && ChangeDisplaySettings( &DevMode, CDS_RESET|CDS_FULLSCREEN ) == DISP_CHANGE_SUCCESSFUL );
}

void ResetScreenMode()
{
    ChangeDisplaySettings( NULL, 0 );
}

void SwapBuffers()
{
    SwapBuffers(hDC);
}

#endif // !C_USE_SDL && WIN32
