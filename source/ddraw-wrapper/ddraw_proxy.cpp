//**************************************************************
//* ddraw_proxy.cpp - logging + forwarding DirectDraw proxy for Incubation.
//*
//* Purpose (recon phase): forward every DirectDraw call to the real
//* implementation (dgVoodoo's ddraw, renamed to ddraw_impl.dll) while
//* logging the calls that matter for building a 2D compositor:
//*   - display mode / cooperative level (resolution, fullscreen)
//*   - surface creation (primary/backbuffer/offscreen, size, pixel format)
//*   - Blt / BltFast / Flip / Lock / Unlock on the primary
//*
//* Later phase: instead of forwarding presentation to dgVoodoo, snapshot the
//* primary surface and hand its pixels to glide2x (OpenGlide) to draw as a
//* fullscreen GL overlay on top of the HD 3D - removing dgVoodoo entirely.
//*
//* The game only imports DirectDrawCreate + DirectDrawCreateClipper.
//**************************************************************
#undef CINTERFACE          // force C++ abstract-class interfaces, not C fn-pointer structs
#include <windows.h>
#include <ddraw.h>
#include <cstdio>

static HMODULE g_impl = NULL;
static FILE   *g_log  = NULL;

static void LG( const char *fmt, ... )
{
    if ( !g_log )
    {
        g_log = fopen( "ddraw_proxy.log", "wt" );
        if ( !g_log ) return;
    }
    va_list ap; va_start( ap, fmt );
    vfprintf( g_log, fmt, ap );
    va_end( ap );
    fflush( g_log );
}

static void LoadImpl()
{
    if ( g_impl ) return;
    g_impl = LoadLibraryA( "ddraw_impl.dll" );   // the renamed dgVoodoo ddraw
    LG( "LoadImpl ddraw_impl.dll -> %p\n", (void*)g_impl );
}

typedef HRESULT (WINAPI *DDRAWCREATE)( GUID*, LPDIRECTDRAW*, IUnknown* );
typedef HRESULT (WINAPI *DDRAWCREATECLIP)( DWORD, LPDIRECTDRAWCLIPPER*, IUnknown* );

//--------------------------------------------------------------- surface wrapper
class WrapSurface : public IDirectDrawSurface
{
public:
    IDirectDrawSurface *inner;
    const char         *tag;
    WrapSurface( IDirectDrawSurface *s, const char *t ) : inner( s ), tag( t ) {}

    // IUnknown
    STDMETHOD(QueryInterface)( REFIID r, void** o ) { return inner->QueryInterface( r, o ); }
    STDMETHOD_(ULONG,AddRef)()  { return inner->AddRef(); }
    STDMETHOD_(ULONG,Release)() { ULONG n = inner->Release(); if ( n == 0 ) delete this; return n; }
    // IDirectDrawSurface
    STDMETHOD(AddAttachedSurface)( LPDIRECTDRAWSURFACE s ) { return inner->AddAttachedSurface( s ); }
    STDMETHOD(AddOverlayDirtyRect)( LPRECT r ) { return inner->AddOverlayDirtyRect( r ); }
    STDMETHOD(Blt)( LPRECT d, LPDIRECTDRAWSURFACE src, LPRECT s, DWORD f, LPDDBLTFX fx )
    {
        LG( "%s Blt dst=%p src=%p flags=%08x\n", tag, (void*)d, (void*)src, f );
        WrapSurface *w = (WrapSurface*)src;
        return inner->Blt( d, w ? w->inner : NULL, s, f, fx );
    }
    STDMETHOD(BltBatch)( LPDDBLTBATCH b, DWORD c, DWORD f ) { return inner->BltBatch( b, c, f ); }
    STDMETHOD(BltFast)( DWORD x, DWORD y, LPDIRECTDRAWSURFACE src, LPRECT s, DWORD f )
    {
        LG( "%s BltFast %lu,%lu src=%p flags=%08x\n", tag, x, y, (void*)src, f );
        WrapSurface *w = (WrapSurface*)src;
        return inner->BltFast( x, y, w ? w->inner : NULL, s, f );
    }
    STDMETHOD(DeleteAttachedSurface)( DWORD f, LPDIRECTDRAWSURFACE s ) { return inner->DeleteAttachedSurface( f, s ); }
    STDMETHOD(EnumAttachedSurfaces)( LPVOID c, LPDDENUMSURFACESCALLBACK cb ) { return inner->EnumAttachedSurfaces( c, cb ); }
    STDMETHOD(EnumOverlayZOrders)( DWORD f, LPVOID c, LPDDENUMSURFACESCALLBACK cb ) { return inner->EnumOverlayZOrders( f, c, cb ); }
    STDMETHOD(Flip)( LPDIRECTDRAWSURFACE s, DWORD f )
    {
        LG( "%s Flip flags=%08x\n", tag, f );
        WrapSurface *w = (WrapSurface*)s;
        return inner->Flip( w ? w->inner : NULL, f );
    }
    STDMETHOD(GetAttachedSurface)( LPDDSCAPS c, LPDIRECTDRAWSURFACE* s )
    {
        HRESULT hr = inner->GetAttachedSurface( c, s );
        if ( SUCCEEDED( hr ) && s && *s )
        {
            LG( "%s GetAttachedSurface caps=%08x -> wrapped backbuffer\n", tag, c ? c->dwCaps : 0 );
            *s = new WrapSurface( *s, "BACK" );
        }
        return hr;
    }
    STDMETHOD(GetBltStatus)( DWORD f ) { return inner->GetBltStatus( f ); }
    STDMETHOD(GetCaps)( LPDDSCAPS c ) { return inner->GetCaps( c ); }
    STDMETHOD(GetClipper)( LPDIRECTDRAWCLIPPER* c ) { return inner->GetClipper( c ); }
    STDMETHOD(GetColorKey)( DWORD f, LPDDCOLORKEY k ) { return inner->GetColorKey( f, k ); }
    STDMETHOD(GetDC)( HDC* h ) { return inner->GetDC( h ); }
    STDMETHOD(GetFlipStatus)( DWORD f ) { return inner->GetFlipStatus( f ); }
    STDMETHOD(GetOverlayPosition)( LPLONG x, LPLONG y ) { return inner->GetOverlayPosition( x, y ); }
    STDMETHOD(GetPalette)( LPDIRECTDRAWPALETTE* p ) { return inner->GetPalette( p ); }
    STDMETHOD(GetPixelFormat)( LPDDPIXELFORMAT f ) { return inner->GetPixelFormat( f ); }
    STDMETHOD(GetSurfaceDesc)( LPDDSURFACEDESC d ) { return inner->GetSurfaceDesc( d ); }
    STDMETHOD(Initialize)( LPDIRECTDRAW dd, LPDDSURFACEDESC d ) { return inner->Initialize( dd, d ); }
    STDMETHOD(IsLost)() { return inner->IsLost(); }
    STDMETHOD(Lock)( LPRECT r, LPDDSURFACEDESC d, DWORD f, HANDLE h )
    {
        HRESULT hr = inner->Lock( r, d, f, h );
        static int n = 0;
        if ( n < 8 && SUCCEEDED( hr ) && d )
        {
            LG( "%s Lock -> %lux%lu pitch=%ld bpp=%lu flags=%08x\n", tag,
                d->dwWidth, d->dwHeight, d->lPitch,
                d->ddpfPixelFormat.dwRGBBitCount, f );
            n++;
        }
        return hr;
    }
    STDMETHOD(ReleaseDC)( HDC h ) { return inner->ReleaseDC( h ); }
    STDMETHOD(Restore)() { return inner->Restore(); }
    STDMETHOD(SetClipper)( LPDIRECTDRAWCLIPPER c ) { return inner->SetClipper( c ); }
    STDMETHOD(SetColorKey)( DWORD f, LPDDCOLORKEY k )
    {
        LG( "%s SetColorKey flags=%08x\n", tag, f );
        return inner->SetColorKey( f, k );
    }
    STDMETHOD(SetOverlayPosition)( LONG x, LONG y ) { return inner->SetOverlayPosition( x, y ); }
    STDMETHOD(SetPalette)( LPDIRECTDRAWPALETTE p ) { return inner->SetPalette( p ); }
    STDMETHOD(Unlock)( LPVOID p ) { return inner->Unlock( p ); }
    STDMETHOD(UpdateOverlay)( LPRECT sr, LPDIRECTDRAWSURFACE d, LPRECT dr, DWORD f, LPDDOVERLAYFX fx )
    { WrapSurface *w = (WrapSurface*)d; return inner->UpdateOverlay( sr, w?w->inner:NULL, dr, f, fx ); }
    STDMETHOD(UpdateOverlayDisplay)( DWORD f ) { return inner->UpdateOverlayDisplay( f ); }
    STDMETHOD(UpdateOverlayZOrder)( DWORD f, LPDIRECTDRAWSURFACE s )
    { WrapSurface *w = (WrapSurface*)s; return inner->UpdateOverlayZOrder( f, w?w->inner:NULL ); }
};

//--------------------------------------------------------------- ddraw wrapper
class WrapDD : public IDirectDraw
{
public:
    IDirectDraw *inner;
    WrapDD( IDirectDraw *d ) : inner( d ) {}

    STDMETHOD(QueryInterface)( REFIID r, void** o ) { return inner->QueryInterface( r, o ); }
    STDMETHOD_(ULONG,AddRef)()  { return inner->AddRef(); }
    STDMETHOD_(ULONG,Release)() { ULONG n = inner->Release(); if ( n == 0 ) delete this; return n; }

    STDMETHOD(Compact)() { return inner->Compact(); }
    STDMETHOD(CreateClipper)( DWORD f, LPDIRECTDRAWCLIPPER* c, IUnknown* u ) { return inner->CreateClipper( f, c, u ); }
    STDMETHOD(CreatePalette)( DWORD f, LPPALETTEENTRY e, LPDIRECTDRAWPALETTE* p, IUnknown* u )
    { LG( "CreatePalette flags=%08x\n", f ); return inner->CreatePalette( f, e, p, u ); }
    STDMETHOD(CreateSurface)( LPDDSURFACEDESC d, LPDIRECTDRAWSURFACE* s, IUnknown* u )
    {
        HRESULT hr = inner->CreateSurface( d, s, u );
        if ( SUCCEEDED( hr ) && s && *s )
        {
            DWORD caps = ( d && ( d->dwFlags & DDSD_CAPS ) ) ? d->ddsCaps.dwCaps : 0;
            DWORD w = ( d && ( d->dwFlags & DDSD_WIDTH ) )  ? d->dwWidth  : 0;
            DWORD h = ( d && ( d->dwFlags & DDSD_HEIGHT ) ) ? d->dwHeight : 0;
            const char *tag = ( caps & DDSCAPS_PRIMARYSURFACE ) ? "PRIMARY" : "OFFSCR";
            LG( "CreateSurface caps=%08x %lux%lu bb=%lu -> %s\n", caps, w, h,
                ( d && ( d->dwFlags & DDSD_BACKBUFFERCOUNT ) ) ? d->dwBackBufferCount : 0, tag );
            *s = new WrapSurface( *s, ( caps & DDSCAPS_PRIMARYSURFACE ) ? "PRIMARY" : "OFFSCR" );
        }
        return hr;
    }
    STDMETHOD(DuplicateSurface)( LPDIRECTDRAWSURFACE s, LPDIRECTDRAWSURFACE* d )
    { WrapSurface *w = (WrapSurface*)s; return inner->DuplicateSurface( w?w->inner:NULL, d ); }
    STDMETHOD(EnumDisplayModes)( DWORD f, LPDDSURFACEDESC d, LPVOID c, LPDDENUMMODESCALLBACK cb )
    { return inner->EnumDisplayModes( f, d, c, cb ); }
    STDMETHOD(EnumSurfaces)( DWORD f, LPDDSURFACEDESC d, LPVOID c, LPDDENUMSURFACESCALLBACK cb )
    { return inner->EnumSurfaces( f, d, c, cb ); }
    STDMETHOD(FlipToGDISurface)() { return inner->FlipToGDISurface(); }
    STDMETHOD(GetCaps)( LPDDCAPS a, LPDDCAPS b ) { return inner->GetCaps( a, b ); }
    STDMETHOD(GetDisplayMode)( LPDDSURFACEDESC d ) { return inner->GetDisplayMode( d ); }
    STDMETHOD(GetFourCCCodes)( LPDWORD n, LPDWORD c ) { return inner->GetFourCCCodes( n, c ); }
    STDMETHOD(GetGDISurface)( LPDIRECTDRAWSURFACE* s ) { return inner->GetGDISurface( s ); }
    STDMETHOD(GetMonitorFrequency)( LPDWORD f ) { return inner->GetMonitorFrequency( f ); }
    STDMETHOD(GetScanLine)( LPDWORD l ) { return inner->GetScanLine( l ); }
    STDMETHOD(GetVerticalBlankStatus)( LPBOOL b ) { return inner->GetVerticalBlankStatus( b ); }
    STDMETHOD(Initialize)( GUID* g ) { return inner->Initialize( g ); }
    STDMETHOD(RestoreDisplayMode)() { LG( "RestoreDisplayMode\n" ); return inner->RestoreDisplayMode(); }
    STDMETHOD(SetCooperativeLevel)( HWND h, DWORD f )
    { LG( "SetCooperativeLevel hwnd=%p flags=%08x\n", (void*)h, f ); return inner->SetCooperativeLevel( h, f ); }
    STDMETHOD(SetDisplayMode)( DWORD w, DWORD h, DWORD bpp )
    { LG( "SetDisplayMode %lux%lu %lubpp\n", w, h, bpp ); return inner->SetDisplayMode( w, h, bpp ); }
    STDMETHOD(WaitForVerticalBlank)( DWORD f, HANDLE h ) { return inner->WaitForVerticalBlank( f, h ); }
};

//--------------------------------------------------------------- exports
extern "C" HRESULT WINAPI DirectDrawCreate( GUID* guid, LPDIRECTDRAW* dd, IUnknown* unk )
{
    LoadImpl();
    LG( "DirectDrawCreate\n" );
    DDRAWCREATE real = (DDRAWCREATE)GetProcAddress( g_impl, "DirectDrawCreate" );
    if ( !real ) { LG( "  real DirectDrawCreate missing!\n" ); return E_FAIL; }
    LPDIRECTDRAW raw = NULL;
    HRESULT hr = real( guid, &raw, unk );
    if ( SUCCEEDED( hr ) && raw )
    {
        *dd = new WrapDD( (IDirectDraw*)raw );
        LG( "  wrapped IDirectDraw %p -> %p\n", (void*)raw, (void*)*dd );
    }
    return hr;
}

extern "C" HRESULT WINAPI DirectDrawCreateClipper( DWORD flags, LPDIRECTDRAWCLIPPER* clip, IUnknown* unk )
{
    LoadImpl();
    LG( "DirectDrawCreateClipper flags=%08x\n", flags );
    DDRAWCREATECLIP real = (DDRAWCREATECLIP)GetProcAddress( g_impl, "DirectDrawCreateClipper" );
    if ( !real ) return E_FAIL;
    return real( flags, clip, unk );
}

BOOL WINAPI DllMain( HINSTANCE, DWORD reason, LPVOID )
{
    if ( reason == DLL_PROCESS_ATTACH ) LG( "=== ddraw_proxy attached ===\n" );
    return TRUE;
}
