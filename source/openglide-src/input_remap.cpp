//**************************************************************
//* input_remap.cpp - translate mouse coordinates from the real
//* (fullscreen-sized) window client space back into the 640x480
//* Glide space the game thinks in. Installed only when the
//* window is bigger than the Glide resolution; identity (never
//* installed) in the native small-window mode.
//*
//* The mapping is the inverse of the pillarbox used for rendering:
//*   phys_x = glide_x * scale + xoff   =>  glide_x = (phys_x - xoff) / scale
//*   phys_y = glide_y * scale          =>  glide_y =  phys_y / scale
//**************************************************************
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <windows.h>
#include "GlOgl.h"

static WNDPROC OrigWndProc = NULL;
static HWND    HookedWnd   = NULL;
static int     MsgLogCount = 0;
// dgVoodoo's CaptureMouse may ALREADY deliver coords in 640x480 space.
// Only rescale if we actually observe coordinates beyond the Glide space.
static bool    CoordsArePhysical = false;

static void PhysToGlide( int px, int py, int &gx, int &gy )
{
    double scale = (double)OpenGL.WindowHeight / (double)Glide.WindowHeight;
    int    xoff  = (int)( ( (double)OpenGL.WindowWidth -
                            (double)Glide.WindowWidth * scale ) / 2.0 );
    if ( scale <= 0.0 )
    {
        scale = 1.0;
    }
    gx = (int)( ( px - xoff ) / scale );
    gy = (int)( py / scale );
    if ( gx < 0 ) gx = 0;
    if ( gx > (int)Glide.WindowWidth  - 1 ) gx = Glide.WindowWidth  - 1;
    if ( gy < 0 ) gy = 0;
    if ( gy > (int)Glide.WindowHeight - 1 ) gy = Glide.WindowHeight - 1;
}

static bool ScalingActive( void )
{
    return (int)OpenGL.WindowWidth  > (int)Glide.WindowWidth &&
           (int)OpenGL.WindowHeight > (int)Glide.WindowHeight;
}

static void GlideToPhys( int gx, int gy, int &px, int &py )
{
    double scale = (double)OpenGL.WindowHeight / (double)Glide.WindowHeight;
    int    xoff  = (int)( ( (double)OpenGL.WindowWidth -
                            (double)Glide.WindowWidth * scale ) / 2.0 );
    px = (int)( gx * scale ) + xoff;
    py = (int)( gy * scale );
}

//--------------------------------------------------------------
// IAT hooks: the game itself calls ClipCursor(0,0,640,480) - it is sure its
// window is that big - which cages the physical cursor in the top-left corner
// of the fullscreen window. GetCursorPos/SetCursorPos get the same treatment
// so every cursor API the game uses speaks 640x480 while the real cursor
// roams the whole window.
//--------------------------------------------------------------
static BOOL ( WINAPI *Real_ClipCursor )( const RECT * )   = ClipCursor;
static BOOL ( WINAPI *Real_GetCursorPos )( LPPOINT )      = GetCursorPos;
static BOOL ( WINAPI *Real_SetCursorPos )( int, int )     = SetCursorPos;
static int  ApiLogCount = 0;

static BOOL WINAPI My_ClipCursor( const RECT *rect )
{
    if ( rect == NULL || !ScalingActive( ) || HookedWnd == NULL )
    {
        return Real_ClipCursor( rect );
    }
    // the game asks for its imagined 640x480 area: give it the real,
    // pillarboxed image rectangle instead (in screen coordinates)
    int l, t, r, b;
    GlideToPhys( 0, 0, l, t );
    GlideToPhys( Glide.WindowWidth, Glide.WindowHeight, r, b );
    POINT lt = { l, t }, rb = { r, b };
    ClientToScreen( HookedWnd, &lt );
    ClientToScreen( HookedWnd, &rb );
    RECT big = { lt.x, lt.y, rb.x, rb.y };
    if ( ApiLogCount < 20 )
    {
        GlideMsg( "ClipCursor (%ld,%ld,%ld,%ld) -> (%ld,%ld,%ld,%ld)\n",
                  rect->left, rect->top, rect->right, rect->bottom,
                  big.left, big.top, big.right, big.bottom );
        ApiLogCount++;
    }
    return Real_ClipCursor( &big );
}

static BOOL WINAPI My_GetCursorPos( LPPOINT pt )
{
    BOOL ok = Real_GetCursorPos( pt );
    if ( ok && ScalingActive( ) && HookedWnd != NULL )
    {
        POINT c = *pt;
        ScreenToClient( HookedWnd, &c );
        int gx, gy;
        PhysToGlide( c.x, c.y, gx, gy );
        POINT g = { gx, gy };
        ClientToScreen( HookedWnd, &g );   // back to "screen" as the game expects
        if ( ApiLogCount < 30 )
        {
            GlideMsg( "GetCursorPos %ld,%ld -> %ld,%ld\n", pt->x, pt->y, g.x, g.y );
            ApiLogCount++;
        }
        *pt = g;
    }
    return ok;
}

static BOOL WINAPI My_SetCursorPos( int x, int y )
{
    if ( ScalingActive( ) && HookedWnd != NULL )
    {
        POINT g = { x, y };
        ScreenToClient( HookedWnd, &g );
        int px, py;
        GlideToPhys( g.x, g.y, px, py );
        POINT p = { px, py };
        ClientToScreen( HookedWnd, &p );
        if ( ApiLogCount < 20 )
        {
            GlideMsg( "SetCursorPos %d,%d -> %ld,%ld\n", x, y, p.x, p.y );
            ApiLogCount++;
        }
        return Real_SetCursorPos( p.x, p.y );
    }
    return Real_SetCursorPos( x, y );
}

// patch one module's user32 import entries
static void PatchModuleIAT( HMODULE mod, const char *modname )
{
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)mod;
    if ( dos->e_magic != IMAGE_DOS_SIGNATURE ) return;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)( (BYTE *)mod + dos->e_lfanew );
    if ( nt->Signature != IMAGE_NT_SIGNATURE ) return;
    DWORD impRVA = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if ( !impRVA ) return;

    for ( IMAGE_IMPORT_DESCRIPTOR *imp =
              (IMAGE_IMPORT_DESCRIPTOR *)( (BYTE *)mod + impRVA );
          imp->Name; imp++ )
    {
        const char *dll = (const char *)mod + imp->Name;
        if ( lstrcmpiA( dll, "user32.dll" ) != 0 ) continue;
        if ( !imp->OriginalFirstThunk ) continue;   // no name table - can't match

        IMAGE_THUNK_DATA *orig = (IMAGE_THUNK_DATA *)( (BYTE *)mod + imp->OriginalFirstThunk );
        IMAGE_THUNK_DATA *iat  = (IMAGE_THUNK_DATA *)( (BYTE *)mod + imp->FirstThunk );
        for ( ; orig->u1.AddressOfData; orig++, iat++ )
        {
            if ( orig->u1.Ordinal & IMAGE_ORDINAL_FLAG ) continue;
            IMAGE_IMPORT_BY_NAME *ibn =
                (IMAGE_IMPORT_BY_NAME *)( (BYTE *)mod + orig->u1.AddressOfData );
            const char *fn = (const char *)ibn->Name;
            void *repl = NULL;
            if      ( !lstrcmpA( fn, "ClipCursor" ) )   repl = (void *)My_ClipCursor;
            else if ( !lstrcmpA( fn, "GetCursorPos" ) ) repl = (void *)My_GetCursorPos;
            else if ( !lstrcmpA( fn, "SetCursorPos" ) ) repl = (void *)My_SetCursorPos;
            if ( !repl ) continue;

            DWORD prot;
            if ( VirtualProtect( &iat->u1.Function, sizeof( void * ),
                                 PAGE_READWRITE, &prot ) )
            {
                iat->u1.Function = (DWORD)repl;
                VirtualProtect( &iat->u1.Function, sizeof( void * ), prot, &prot );
                GlideMsg( "IAT hook: %s!%s\n", modname, fn );
            }
        }
    }
}

static void InstallApiHooks( void )
{
    static bool done = false;
    if ( done ) return;
    done = true;

    // only the game's own modules - NOT ddraw (dgVoodoo) or system DLLs
    static const char *mods[] = { NULL /* exe */, "BGLWin.dll", "NewToolsR.dll",
                                  "ENGWLIB.DLL", "ENG3DFX.DLL", "aWin.dll" };
    for ( unsigned i = 0; i < sizeof( mods ) / sizeof( mods[0] ); i++ )
    {
        HMODULE m = GetModuleHandleA( mods[i] );
        if ( m )
        {
            PatchModuleIAT( m, mods[i] ? mods[i] : "Incubation.exe" );
        }
    }
    // free any cage the game installed before we hooked
    Real_ClipCursor( NULL );
}

// Defined in window.cpp - keep the game's gamma boost only while it's focused,
// so the desktop (especially HDR) never stays dark after alt-tab or exit.
extern void ApplyGameGamma( void );
extern void RestoreDesktopGamma( void );

static LRESULT CALLBACK RemapWndProc( HWND hwnd, UINT msg, WPARAM wp, LPARAM lp )
{
    switch ( msg )
    {
    case WM_ACTIVATEAPP:
        if ( wp )  ApplyGameGamma( );
        else       RestoreDesktopGamma( );
        break;
    case WM_MOUSEMOVE:
    case WM_LBUTTONDOWN: case WM_LBUTTONUP: case WM_LBUTTONDBLCLK:
    case WM_RBUTTONDOWN: case WM_RBUTTONUP: case WM_RBUTTONDBLCLK:
    case WM_MBUTTONDOWN: case WM_MBUTTONUP: case WM_MBUTTONDBLCLK:
        {
            int px = (short)LOWORD( lp );
            int py = (short)HIWORD( lp );

            if ( !CoordsArePhysical &&
                 ( px > (int)Glide.WindowWidth + 8 ||
                   py > (int)Glide.WindowHeight + 8 ) )
            {
                CoordsArePhysical = true;
                GlideMsg( "mouse coords are physical (saw %d,%d) - rescaling ON\n",
                          px, py );
            }

            if ( CoordsArePhysical )
            {
                int gx, gy;
                PhysToGlide( px, py, gx, gy );
                if ( MsgLogCount < 40 )
                {
                    GlideMsg( "mouse 0x%03x phys %d,%d -> glide %d,%d\n",
                              msg, px, py, gx, gy );
                    MsgLogCount++;
                }
                lp = MAKELPARAM( (WORD)gx, (WORD)gy );
            }
            else if ( MsgLogCount < 40 )
            {
                GlideMsg( "mouse 0x%03x %d,%d (pre-mapped, pass-through)\n",
                          msg, px, py );
                MsgLogCount++;
            }
        }
        break;

    case WM_SETCURSOR:
        // someone (dgVoodoo) turns the system cursor off expecting to draw an
        // emulated one that never appears in our hybrid setup - force the
        // ShowCursor counter back to visible while over our client area
        if ( LOWORD( lp ) == HTCLIENT )
        {
            int c = ShowCursor( TRUE );
            while ( c < 0 )  { c = ShowCursor( TRUE );  }
            while ( c > 0 )  { c = ShowCursor( FALSE ); }
            if ( MsgLogCount < 40 )
            {
                GlideMsg( "WM_SETCURSOR: cursor counter normalized to 0\n" );
                MsgLogCount++;
            }
        }
        break;
    }
    return CallWindowProc( OrigWndProc, hwnd, msg, wp, lp );
}

void InstallInputRemap( void *wnd )
{
    HWND hwnd = (HWND)wnd;

    if ( hwnd == NULL || HookedWnd == hwnd )
    {
        return;
    }
    OrigWndProc = (WNDPROC)SetWindowLongPtrA( hwnd, GWLP_WNDPROC,
                                              (LONG_PTR)RemapWndProc );
    HookedWnd = hwnd;
    GlideMsg( "Input remap installed (window %dx%d, glide %dx%d)\n",
              OpenGL.WindowWidth, OpenGL.WindowHeight,
              Glide.WindowWidth, Glide.WindowHeight );
    InstallApiHooks( );
}

void RemoveInputRemap( void )
{
    if ( HookedWnd != NULL && OrigWndProc != NULL )
    {
        SetWindowLongPtrA( HookedWnd, GWLP_WNDPROC, (LONG_PTR)OrigWndProc );
        HookedWnd   = NULL;
        OrigWndProc = NULL;
    }
}
