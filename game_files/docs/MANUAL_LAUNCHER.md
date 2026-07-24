LAUNCHER — що він робить сам / what it does on its own
==============================================================================

Цей файл існує з однієї причини: лаунчер робить чимало речей автоматично —
перевіряє, підміняє, перейменовує, відкочує. Через півроку ми самі не
згадаємо, що саме. Тут перелічено ВСЕ, що він робить без явної команди.

This file exists for one reason: the launcher does a lot automatically —
checks, swaps, renames, restores. In six months we will not remember what.
Everything it does without being asked is listed here.


УКРАЇНСЬКОЮ
------------------------------------------------------------------------------

## 1. При запуску лаунчера

• Перевіряє Windows 10/11-патч
  Рахує md5 файлів audio.dll і sound.dll і порівнює з відомим значенням
  патченої збірки (88e3333beda14ed61f1ca394c43f7413, 52 750 Б, обидва файли
  однакові). Якщо не збігається — угорі вікна з'являється червоне попередження
  з кнопкою на сторінку патча. Без цього патча гра на Win10/11 вішається на
  старті без вікна, і симптом ніяк не пояснює причину.
  Формулювання навмисне м'яке («не схоже, що застосований»), бо новіша версія
  патча матиме інший хеш — і стверджувати «не встановлений» було б брехнею.

• Повертає підмінену тестову мапу
  Якщо попередній сеанс впав із підставленою мапою в слоті _C_100, вона
  повертається на місце. Маркер: backup\maps\swapped.txt.

• Повертає HD-пак, якщо він лишився на паузі
  Маркер: backup\hd_pack_paused.txt. Див. пункт 3.

• Страхує наш glide2x.dll (secure_our_build)
  Якщо backup\glide2x.dll.openglide ще немає, а встановлений glide2x.dll — наш
  (містить INCU_SHARP), він одразу копіюється в бекап. Причина у Windows-пастці:
  glide2x.dll і Glide2x.dll — це ОДИН файл (регістр не має значення), тож коли
  хтось кладе Glide2x.dll від dgVoodoo в теку гри, він перезаписує наш. Якщо
  наш білд уже в бекапі — HD-режим завжди його відновить; якби він був лише в
  живому слоті, така заміна втратила б його назавжди.

• Створює потрібні теки (ensure_dirs)
  backup\ і dgVoodoo\, і кладе в dgVoodoo\ readme з поясненням. Тож свіжа
  установка ніколи не лишається без потрібної теки.

• dgVoodoo береться ТІЛЬКИ з теки dgVoodoo\ (user_dgvoodoo, user_dgvoodoo_ddraw)
  Лаунчер більше не сканує теку гри на «якийсь враппер» — саме це раніше хапало
  стокові glide.dll/glide3x.dll гри (Glide 1.x/3.x) і валило її помилкою
  «entry point _ConvertAndDownloadRle@64 not found». Тепер правило просте:
  кладеш валідний 32-біт glide2x.dll у dgVoodoo\ — Vanilla йде через нього;
  не кладеш — Vanilla йде нашим рендерером з паузою HD-паку. Файл перевіряється
  за вмістом (символ _ConvertAndDownloadRle@64), тож помилково кинута стокова
  glide.dll просто ігнорується, а не встановлюється. Ім'я значення не має.
  Туди ж кладеться ddraw.dll від dgVoodoo — він вмикає перемикач «Vanilla via →
  DirectX» (перевірка за вмістом: експортує DirectDrawCreate і містить рядок
  «dgVoodoo», який лежить у ресурсі версії, тобто в UTF-16).

• Прибирає ddraw.dll, якщо попередній запуск впав (restore_ddraw)
  DirectX-режим кладе ddraw.dll від dgVoodoo в теку гри лише на час сеансу. Якщо
  гра чи лаунчер завершилися аварійно, маркер backup\ddraw_installed.txt лишиться
  — і на наступному старті файл прибирається, а те, що лежало там раніше,
  повертається з backup\ddraw.dll.orig.

• Перевіряє Pillow
  Якщо його немає в тому Python, під яким запущено лаунчер — у рядку статусу
  з'являється точна команда встановлення саме для цього інтерпретатора.

## 2. При натисканні Launch

• Обирає ключ рендерера для гри
  Гра бере рендерер з командного рядка: -3dfx йде через ENG3DFX.DLL на Glide,
  -directx — через DDRAW.DLL на DirectDraw. Обидва пропускають перевірку CD 1997
  року й не потребують підвищення прав. HD завжди -3dfx (наш форк — це Glide-
  враппер). Vanilla слухає перемикач «Vanilla via» на вкладці Play: DirectX
  ставить ddraw.dll від dgVoodoo в теку гри й запускає -directx (логотип
  dgVoodoo, миша працює), Glide лишає -3dfx (логотип 3dfx). Курсор працює саме на
  DirectX-шляху, бо обробка курсора в dgVoodoo прив'язана до нього —
  SystemHookFlags у dgVoodoo.conf описаний як «x86-DX only».

• Ставить потрібний glide2x.dll у живий слот
  HD → наша збірка (з backup\glide2x.dll.openglide). Vanilla → dgVoodoo з
  теки dgVoodoo\, якщо він там є; якщо ні — теж наша збірка, але з паузою
  HD-паку. У DirectX-режимі glide2x взагалі не чіпається — він там ні до чого.
  Перед підміною наша збірка страхується в бекап (див. пункт 1), тож вона ніколи
  не губиться. Класти щось у glide2x.dll вручну немає сенсу — при наступному
  запуску його перезапише.

• Приймає нашу збірку в бекап, якщо його ще немає
  Свіжа установка з реліз-кіту не має теки backup\ взагалі. Якщо
  backup\glide2x.dll.openglide відсутній, а встановлений glide2x.dll — наша
  збірка (містить INCU_SHARP) — файл копіюється в бекап як еталон.

• Якщо dgVoodoo немає — не глухий кут
  Запускає наш рендерер, поставивши HD-пак на паузу на час сеансу (див. 3).
  Різницю між vanilla і HD робить саме підстановка текстур, тож для порівняння
  й перегляду ванільних правок цього достатньо. Стокові glide.dll/glide3x.dll
  гри при цьому НЕ чіпаються.

• Виставляє змінні середовища (тільки в режимі HD)
  INCU_SHARP, INCU_BUMP, INCU_STRETCH, __COMPAT_LAYER=HIGHDPIAWARE.
  У режимі Vanilla вони навпаки прибираються з оточення.

• Міняє роздільність екрана (тільки HD) і повертає її після виходу.

• Підставляє обрану тестову мапу в слот _C_100 і повертає оригінал після виходу.

## 3. Пауза HD-паку

Робиться лише у Vanilla-режимі, коли dgVoodoo недоступний. Тека hd_pack_hd
перейменовується на hd_pack_hd.off, створюється маркер
backup\hd_pack_paused.txt. Після виходу з гри все повертається. Якщо гра або
лаунчер впадуть — пак поверне наступний старт лаунчера за маркером.

## 4. Що лаунчер НЕ робить

• Не чіпає файли гри, крім glide2x.dll і слоту тестової мапи.
• Не чіпає texture.lib — це робить вкладка Vanilla textures, і лише за
  явним натисканням Install, з бекапом оригіналів у
  backup\<світ>_TEXTURES.orig\.
• Не качає нічого з інтернету. Вкладка Links лише відкриває сторінки в браузері.

## 5. Іменування у теці backup\

У backup\ лежить наша збірка glide2x.dll.openglide (еталон для HD) і, за
потреби, попередні наші збірки glide2x.dll.openglide.pre-* для відкату.
dgVoodoo тут НЕ зберігається — він живе в окремій теці dgVoodoo\ (див. пункт 1).
⚠️ Не копіюй dgVoodoo'шний Glide2x.dll просто в теку гри — Windows вважає
glide2x.dll і Glide2x.dll одним файлом, тож він перезапише наш рендерер. Клади
його в dgVoodoo\ або через кнопку «Set dgVoodoo from a file…» на вкладці Debug.


ENGLISH
------------------------------------------------------------------------------

## 1. On launcher start

• Checks the Windows 10/11 patch — md5 of audio.dll and sound.dll against the
  known patched build (88e3333beda14ed61f1ca394c43f7413, 52 750 B, both files
  identical). On a mismatch a red banner appears with a button to the download
  page. Without the patch the stock game hangs at startup with no window, a
  symptom that explains nothing by itself. The wording is deliberately soft
  ("does not look like it is applied") because a newer patch revision would
  hash differently.
• Restores a test map left swapped into the _C_100 slot by a crashed session
  (marker: backup\maps\swapped.txt).
• Restores an HD pack left paused (marker: backup\hd_pack_paused.txt, see 3).
• Removes dgVoodoo's ddraw.dll if a crashed DirectX run left it in the game
  folder (marker: backup\ddraw_installed.txt), putting back whatever was there
  before from backup\ddraw.dll.orig.
• Checks Pillow, and if missing prints the exact install command for the
  interpreter it is actually running under.

## 2. On Launch

• Picks the game's renderer switch — the game takes it from the command line:
  -3dfx goes through ENG3DFX.DLL to Glide, -directx through DDRAW.DLL to
  DirectDraw. Both skip the 1997 CD check and need no elevation. HD is always
  -3dfx (our fork is a Glide wrapper). Vanilla follows the Play tab's "Vanilla
  via" switch: DirectX installs dgVoodoo's ddraw.dll for the run and launches
  -directx (dgVoodoo logo, working mouse), Glide stays on -3dfx (3dfx logo). The
  cursor only maps correctly on the DirectX path because dgVoodoo's cursor
  handling belongs to it — dgVoodoo.conf documents SystemHookFlags as x86-DX only.
• Installs the right glide2x.dll into the live slot — HD: our build (from
  backup\glide2x.dll.openglide). Vanilla: dgVoodoo from the dgVoodoo\ folder if
  present, otherwise our build with the HD pack paused. In DirectX mode glide2x
  is not touched at all. Our build is secured to the backup first (see 1) so a
  swap can never lose it. Putting a file at glide2x.dll by hand is pointless; it
  gets overwritten.
• Adopts our shipped build into the backup if none exists — a kit install has no
  backup\ folder, so if glide2x.dll carries the INCU_SHARP marker it is copied
  in and used as the reference from then on.
• Falls back gracefully when dgVoodoo is absent: runs our renderer with the HD
  pack paused instead of dead-ending. The game's stock glide.dll/glide3x.dll are
  never touched.
• Sets INCU_SHARP / INCU_BUMP / INCU_STRETCH / __COMPAT_LAYER in HD mode, and
  removes them in Vanilla mode.
• Changes the display mode (HD only) and restores it on exit.
• Swaps the chosen test map into _C_100 and restores it on exit.

## 3. HD pack pause

Vanilla mode without dgVoodoo only: hd_pack_hd is renamed to hd_pack_hd.off
with a marker at backup\hd_pack_paused.txt, and restored when the game exits or
at the next launcher start if something crashed.

## 4. What it does NOT do

• Touches no game files other than glide2x.dll and the test-map slot.
• Never touches texture.lib on its own — only the Vanilla textures tab does,
  on an explicit Install, backing originals up to backup\<world>_TEXTURES.orig\.
• Downloads nothing. The Links tab only opens pages in your browser.

## 5. Naming in backup\

backup\ holds our build glide2x.dll.openglide (the HD reference) and any
earlier builds of ours as glide2x.dll.openglide.pre-* for rollback. dgVoodoo is
NOT kept here -- it lives in its own dgVoodoo\ folder (see 1). WARNING: never
copy dgVoodoo's Glide2x.dll straight into the game folder -- Windows treats
glide2x.dll and Glide2x.dll as one file, so it overwrites our renderer. Put it
in dgVoodoo\, or use "Set dgVoodoo from a file…" on the Debug tab.
