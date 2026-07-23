//**************************************************************
//*            OpenGLide - Incubation HD fork
//*   Aspect-ratio mode for the 640x480 -> window scaling.
//**************************************************************
//
// The game renders a fixed 640x480 (4:3) Glide frame. On a 16:9 screen that
// leaves a choice, and different people want different things:
//
//   INCU_STRETCH=0 (default)  keep 4:3, centred, black bars left and right.
//                             Correct proportions - circles stay circles.
//   INCU_STRETCH=1            stretch to fill the whole screen. No bars, but
//                             everything is ~33% wider on a 16:9 monitor.
//
// Read once at startup, exactly like INCU_SHARP / INCU_BUMP. The macros in
// GlOgl.h branch on this flag; nothing else in the renderer needs to know.

#include <stdlib.h>

bool g_StretchToFill = false;

// Read at DLL load through a static constructor, so no existing file needs an
// init call added to it. The flag is only ever read while drawing, long after.
namespace
{
    struct IncuAspectInit
    {
        IncuAspectInit()
        {
            const char *env = getenv( "INCU_STRETCH" );
            if ( env )
            {
                g_StretchToFill = ( atoi( env ) != 0 );
            }
        }
    };

    IncuAspectInit s_incuAspectInit;
}
