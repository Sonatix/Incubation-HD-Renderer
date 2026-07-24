/* setres.exe - tiny display-resolution helper for the Incubation launch bats.
 *   setres            -> print current desktop mode
 *   setres W H        -> switch desktop to W x H (keeps current depth/refresh)
 *   setres reset      -> restore the registry-default mode
 * Returns 0 on success, 1 on failure. Built with MinGW:
 *   i686 gcc setres.c -o setres.exe -luser32
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    DEVMODE dm;
    memset(&dm, 0, sizeof(dm));
    dm.dmSize = sizeof(dm);

    if (argc < 2 || !strcmp(argv[1], "get")) {
        if (EnumDisplaySettings(NULL, ENUM_CURRENT_SETTINGS, &dm))
            printf("%lux%lu @ %luHz %lubpp\n",
                   dm.dmPelsWidth, dm.dmPelsHeight,
                   dm.dmDisplayFrequency, dm.dmBitsPerPel);
        return 0;
    }

    if (!strcmp(argv[1], "reset")) {
        LONG r = ChangeDisplaySettings(NULL, 0);   /* back to registry default */
        return r == DISP_CHANGE_SUCCESSFUL ? 0 : 1;
    }

    if (argc >= 3) {
        int w = atoi(argv[1]), h = atoi(argv[2]);
        if (w <= 0 || h <= 0) { fprintf(stderr, "bad size\n"); return 1; }
        /* start from the current mode so depth/refresh are preserved */
        EnumDisplaySettings(NULL, ENUM_CURRENT_SETTINGS, &dm);
        dm.dmPelsWidth  = w;
        dm.dmPelsHeight = h;
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
        LONG r = ChangeDisplaySettings(&dm, CDS_FULLSCREEN);
        if (r != DISP_CHANGE_SUCCESSFUL) {
            fprintf(stderr, "ChangeDisplaySettings(%dx%d) failed: %ld\n", w, h, r);
            return 1;
        }
        return 0;
    }
    fprintf(stderr, "usage: setres [get|reset|W H]\n");
    return 1;
}
