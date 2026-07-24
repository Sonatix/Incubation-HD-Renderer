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

• Підхоплює dgVoodoo без перейменування (adopt_dgvoodoo)
  Сканує теку гри й backup\ на будь-яку .dll, яка є справжнім glide2x-враппером,
  але не нашою. Ознака — символ _ConvertAndDownloadRle@64 (перший, який гра
  імпортує з glide2x.dll), А НЕ просто наявність grGlideInit: гра постачає ще
  стокові glide.dll і glide3x.dll (Glide 1.x/3.x), які теж мають grGlideInit,
  але не цей символ — і встановлення такої DLL як glide2x.dll валить гру
  помилкою «entry point _ConvertAndDownloadRle@64 not found». Тому перевірка
  сувора. Наша збірка має INCU_SHARP; валідний glide2x без нього — сторонній
  враппер (dgVoodoo). Наявний backup\glide2x.dll.dgvoodoo теж перевіряється і
  викидається, якщо виявиться невалідним (наслідок старого, ширшого правила).

• Перевіряє Pillow
  Якщо його немає в тому Python, під яким запущено лаунчер — у рядку статусу
  з'являється точна команда встановлення саме для цього інтерпретатора.

## 2. При натисканні Launch

• Ставить потрібний glide2x.dll
  HD → backup\glide2x.dll.openglide, Vanilla → backup\glide2x.dll.dgvoodoo.
  Файл копіюється в теку гри поверх поточного. Тому класти щось у glide2x.dll
  вручну немає сенсу — при наступному запуску його перезапише.

• Приймає нашу збірку в бекап, якщо його ще немає
  Свіжа установка з реліз-кіту не має теки backup\ взагалі. Якщо
  backup\glide2x.dll.openglide відсутній, а встановлений glide2x.dll містить
  рядок INCU_SHARP (тобто це наша збірка) — файл копіюється в бекап і далі
  використовується як еталон. Нічого качати не треба.

• Рятує невідому збірку перед підміною на dgVoodoo
  Якщо в грі лежить glide2x.dll, який не збігається з жодним бекапом, це
  вважається свіжозібраним dev-білдом OpenGlide. Для HD-запуску він лишається
  як є; перед тим як його перезапише dgVoodoo, він зберігається як новий
  backup\glide2x.dll.openglide. Збірка ніколи не втрачається.

• Якщо dgVoodoo немає — не глухий кут
  Показує, звідки його взяти, і запускає наш рендерер, поставивши HD-пак на
  паузу на час сеансу (див. 3). Різницю між vanilla і HD робить саме
  підстановка текстур, тож для порівняння й перегляду ванільних правок цього
  достатньо.

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

У backup\ лежить кілька варіантів ОДНОГО файлу glide2x.dll, тому вони
розрізняються суфіксом:
    glide2x.dll.openglide          наша збірка (еталон для HD)
    glide2x.dll.dgvoodoo           сток від dgVoodoo (для Vanilla)
    glide2x.dll.openglide.pre-*    попередні наші збірки, для відкату
Але вручну перейменовувати НЕ треба: кнопка «Install dgVoodoo from a file…» на
вкладці Debug сама покладе файл під потрібним іменем, а автопідхоплення (1)
впізнає dgVoodoo за вмістом. ⚠️ Не копіюй Glide2x.dll просто в теку гри —
Windows вважає glide2x.dll і Glide2x.dll одним файлом, тож він перезапише наш
рендерер. Користуйся кнопкою.


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
• Checks Pillow, and if missing prints the exact install command for the
  interpreter it is actually running under.

## 2. On Launch

• Installs the right glide2x.dll — HD from backup\glide2x.dll.openglide,
  Vanilla from backup\glide2x.dll.dgvoodoo, copied over the game's copy. Putting
  a file at glide2x.dll by hand is therefore pointless; it gets overwritten.
• Adopts our shipped build into the backup if none exists — a kit install has no
  backup\ folder, so if glide2x.dll carries the INCU_SHARP marker it is copied
  in and used as the reference from then on.
• Rescues an unrecognised build before dgVoodoo replaces it, stashing it as the
  new backup\glide2x.dll.openglide. A dev build is never lost.
• Falls back gracefully when dgVoodoo is absent: says where to get it and runs
  our renderer with the HD pack paused instead of dead-ending.
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

backup\ holds several variants of the SAME glide2x.dll, told apart by suffix:
    glide2x.dll.openglide          our build (the HD reference)
    glide2x.dll.dgvoodoo           dgVoodoo's stock wrapper (for Vanilla)
    glide2x.dll.openglide.pre-*    earlier builds of ours, for rollback
You do NOT rename it by hand, though: the "Install dgVoodoo from a file…"
button on the Debug tab writes it under the right name, and auto-adopt (1)
recognises dgVoodoo by content. WARNING: never copy Glide2x.dll straight into
the game folder — Windows treats glide2x.dll and Glide2x.dll as one file, so it
overwrites our renderer. Use the button.
