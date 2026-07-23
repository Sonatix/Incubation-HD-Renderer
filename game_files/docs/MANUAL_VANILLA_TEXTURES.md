VANILLA TEXTURES — довідка / manual
==============================================================================

УКРАЇНСЬКОЮ
------------------------------------------------------------------------------

ЩО ЦЕ

Редагування текстур САМОЇ гри. Текстура декодується з texture.lib у PNG, ти
малюєш на ній у будь-якому редакторі, а потім вона кодується назад у формат гри
(VISN) і кладеться в texture.lib. Результат бачить ЗВИЧАЙНА, немодифікована
гра — жодних наших DLL не потрібно. Саме так робляться моди «для всіх».

Дві межі, про які треба знати:
  • Роздільність назавжди 256×256 — двигун вантажить текстуру у фіксований
    буфер. Цей шлях — про ЗМІСТ текстур, не про якість. HD — на вкладці 2.
  • Кодек з утратами (як JPEG): перекодована текстура трохи м'якша за
    оригінал. Намальоване тобою лишається чітким.

ЕЛЕМЕНТИ ВКЛАДКИ

• Library (випадачка)
  Яку бібліотеку редагуємо. 9 світів кампанії + 12 бібліотек відео-роликів.
  World_A00 — це перші місії кампанії (місія називає карту LEVEL01x, а всі
  LEVEL01* лежать саме в World_A00), тому для проби бери його.

• Extract textures
  Декодує всі текстури обраної бібліотеки → visn_work/<світ>/source/*.png.

• Open edit folder
  Відкриває теку правок visn_work/<світ>/edits.

• Вкладка активна лише в режимі Vanilla
  Перемикач HD / Vanilla на вкладці Play — єдиний головний перемикач. Поки він
  стоїть на HD, ця вкладка сіра: у HD-режимі малює наш OpenGlide і підміняє
  текстури з HD-паку, тож правок у .lib однаково не було б видно. Перемкни Play
  на Vanilla — вкладка оживе, а гра піде через стоковий dgVoodoo, який жодних
  підмін не робить.

• Список текстур (ліворуч)
  Зірочка «*» = у цієї текстури вже є твоя правка. Подвійний клік = редагувати.

• Прев'ю «Original in the game» / «Your edit»
  Оригінал і твоя версія поруч — одразу видно, що зміниться.

• Copy to edits + open in editor
  Копіює обраний PNG у теку правок і відкриває у твоєму редакторі зображень.
  Малюй, зберігай (розмір лишай 256×256!) — і повертайся.

• Discard this edit
  Видаляє ТВОЮ правку (оригінал не чіпається).

• Quality (повзунок)
  Якість кодування, 60–100. Стандарт гри — 93, стільки ж використовувала сама
  Blue Byte. Вище ставити нема сенсу: стелю якості визначає кольоровий етап
  формату, тож файл росте, а картинка ні.

• Install into game
  1) Один раз робить бекап незайманих оригіналів у
     backup/<світ>_TEXTURES.orig/  (і більше ніколи його не перезаписує);
  2) перекодовує ТІЛЬКИ текстури з теки правок, решту копіює байт-у-байт;
  3) кладе новий texture.lib (+ .dir/.din) у гру.
  Перепакування завжди йде з чистого бекапу — скільки б разів ти не тиснув
  Install, втрати якості не накопичуються.

• Restore originals
  Повертає незаймані оригінали з бекапу. Правки в edits лишаються — можна
  встановити знову будь-коли.

ПОКРОКОВО

  1. Вкладка Play → перемкни режим на **Vanilla**.
  2. Вкладка Vanilla textures → обери бібліотеку (для перших місій — World_A00).
  3. Extract textures.
  4. Вибери текстуру в списку → Copy to edits + open in editor.
  5. Намалюй / перефарбуй / переклади текст. Зберігай як PNG 256×256.
  6. Install into game.
  7. Назад на Play → Launch vanilla game. Правку видно.
  8. Повернути як було — Restore originals.


ENGLISH
------------------------------------------------------------------------------

WHAT THIS IS

Editing the game's OWN textures. A texture is decoded from texture.lib to PNG,
you paint on it in any editor, and it is re-encoded back into the game's VISN
format and placed into texture.lib. The result is rendered by the plain,
unmodified game — no custom DLLs involved. This is how mods-for-everyone are
made.

Two hard limits to know about:
  • Resolution stays 256×256 forever (fixed engine buffer). This path is about
    texture CONTENT, not quality — HD lives on tab 2.
  • The codec is lossy (JPEG-like): a re-encoded texture is slightly softer
    than the original. Your painted content stays crisp.

TAB ELEMENTS

• Library — which library to edit: 9 campaign worlds + 12 cutscene libraries.
  World_A00 is what the first campaign missions use — start there.
• Extract textures — decodes the whole library → visn_work/<world>/source.
• Open edit folder — opens visn_work/<world>/edits.
• This tab is live only in Vanilla mode — the HD / Vanilla switch on the Play
  tab is the one master control. While Play is set to HD the tab is greyed out,
  because the HD renderer substitutes pack art and .lib edits would be invisible
  anyway. Switch Play to Vanilla and the tab wakes up; the game then runs
  through stock dgVoodoo, which substitutes nothing.
• Texture list — "*" marks textures you have edited; double-click = edit.
• Previews — original vs your edit, side by side.
• Copy to edits + open in editor — copies the PNG into the edit folder and
  opens it in your image editor. Keep it 256×256.
• Discard this edit — deletes your edit (the original is untouched).
• Quality — encoding quality, 60–100. The game's own setting is 93; going
  higher only grows the file (the format's colour stage is the quality
  ceiling).
• Install into game — backs the pristine originals up once
  (backup/<world>_TEXTURES.orig/), re-encodes ONLY the edited textures, copies
  the rest byte-for-byte, and installs the new texture.lib (+ .dir/.din).
  Repacking always starts from the pristine backup, so repeated installs never
  accumulate generation loss.
• Restore originals — puts the untouched library back. Your edits stay in the
  edit folder and can be reinstalled any time.
STEP BY STEP

  1. Play tab → switch the mode to **Vanilla**.
  2. Vanilla textures tab → pick a library (World_A00 for the first missions).
  3. Extract textures.
  4. Select a texture → Copy to edits + open in editor.
  5. Paint / recolour / re-letter it. Save as 256×256 PNG.
  6. Install into game.
  7. Back to Play → Launch vanilla game. The edit is visible.
  8. Restore originals puts everything back.
