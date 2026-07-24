HD TEXTURES — довідка / manual
==============================================================================

УКРАЇНСЬКОЮ
------------------------------------------------------------------------------

ЩО ЦЕ

HD-текстури працюють на рівні рендерера. Гра, як і в 1997-му, вантажить свої
256×256 текстури — а наш OpenGlide (glide2x.dll) у момент завантаження в
відеокарту підміняє їх більшими картинками з паку hd_pack_hd/. Ключ підстановки —
хеш оригінальної текстури, тому імена файлів у паку починаються з 8 hex-символів.

Діє ТІЛЬКИ в режимі «HD» на вкладці Play. Перемикач HD / Vanilla там — єдиний
головний перемикач: поки він на Vanilla, вся ця вкладка сіра (гра йде ванільним
шляхом — через dgVoodoo або через наш рендерер із паузою паку — і HD-пак не
застосовується). Перемкни Play на HD — вкладка оживе.

КНОПКИ ТА ОПЦІЇ

• HD textures (перемикач)
  Вмикає/вимикає весь пак одним рухом (перейменовує теку hd_pack_hd ↔
  hd_pack_hd.off). Вимкнено = гра з оригінальними текстурами. Зручно для
  порівняння «до/після» і для перевірки ванільних правок (вкладка 3) у HD-режимі.

• 1. Extract textures
  Декодує всі унікальні 3D-текстури гри → hd_work/source/<хеш>.png
  (306 унікальних). Достатньо зробити один раз.

• 2. Pack upscaled   ← обов'язковий крок
  Бере hd_work/upscaled/*.png і пише hd_pack_hd/<хеш>.rgba — формат, який
  рендерер читає напряму. Також автоматично оновлює нормал-мапи, чиї джерела
  змінилися. Запускай після КОЖНОЇ зміни файлів у upscaled.

• Generate normal maps
  Робить <хеш>_n.rgba з апскейлених PNG — потрібні лише для ефекту Bump.

• Extract 2D UI
  Витягає спрайти інтерфейсу з Libs/*.LIB → hd_work_2d/ (2296 шт.). Це довідкове:
  вставити їх назад у рендер НЕ можна — гра компонує інтерфейс сама і віддає
  рендереру вже готовий кадр.

• Show status
  Лічильники: скільки витягнуто / апскейлено / запаковано.

• Aspect (на вкладці Play, не тут — але стосується HD)
  Гра малює кадр 640×480, тобто 4:3. На широкому моніторі є два варіанти:
  «Keep 4:3» — чорні смуги ліворуч і праворуч, пропорції правильні (за
  замовчуванням); «Stretch to fill» — на весь екран, але картинка на 16:9 стає
  приблизно на 33 % ширшою. Мишу перераховано під обидва режими, тож курсор
  влучає туди, куди наведений. У режимі Vanilla пропорцією керує dgVoodoo
  (параметр ScalingMode у dgVoodoo.conf), а не ми.

• 2D sharpen (повзунок)
  Різкість 2D-шару (меню, брифінги, портрети). 0 = вимкнено. Технічно це змінна
  INCU_SHARP, яку читає тільки наш OpenGlide — тому в режимі Original не діє.

• Bump strength (повзунок)
  Сила «фейкового рельєфу» на 3D-поверхнях. Працює лише для текстур, поруч з
  якими в паку лежить <хеш>_n.rgba (див. Generate normal maps). 0 = вимкнено.

• Bump diagnostic (галочка)
  Діагностика: замість текстури рендериться сама нормал-мапа — так видно, чи
  вона взагалі підхопилась. Для звичайної гри має бути ВИМКНЕНА.

• Open source / upscaled / pack
  Швидке відкриття трьох робочих тек.

ПОКРОКОВО

  1. Натисни «1. Extract textures» (один раз).
  2. Апскейль PNG-и з hd_work/source будь-яким інструментом (Upscayl,
     Gigapixel, Stable Diffusion…) — розмір будь-який, хоч 4×, хоч 8×.
  3. Поклади результати в hd_work/upscaled. Ім'я мусить починатися з того ж
     хеша; суфікси на кшталт «_out» не заважають (9b5ebc7b_out.png — ок).
  4. Натисни «2. Pack upscaled».
  5. Вкладка Play → режим HD → Launch.
  6. Хочеш порівняти з оригіналом — вимкни перемикач «HD textures» і
     перезапусти гру.

ЗАУВАЖЕННЯ

  Пак можна наповнювати поступово: текстури, яких у паку нема, гра просто
  рендерить як звичайно. Все на цій вкладці безпечне — файли самої гри не
  змінюються взагалі.


ENGLISH
------------------------------------------------------------------------------

WHAT THIS IS

HD works at the renderer level. The game still loads its 256×256 originals, and
our OpenGlide fork (glide2x.dll) substitutes the bigger image from hd_pack_hd/
at texture-upload time, keyed by a hash of the original — which is why every
file in the pack starts with 8 hex characters.

Applies ONLY to "HD" mode on the Play tab. That HD / Vanilla switch is the one
master control: while it is set to Vanilla this whole tab is greyed out (the
game takes the vanilla path -- dgVoodoo, or our renderer with the pack paused --
and the HD pack is never applied). Switch Play back to HD and the tab wakes up.

CONTROLS

• HD textures (toggle) — enables/disables the whole pack (renames hd_pack_hd ↔
  hd_pack_hd.off). Off = original textures; good for A/B comparisons and for
  viewing vanilla texture mods (tab 3) while staying in HD mode.
• 1. Extract textures — decodes every unique 3D texture → hd_work/source
  (306 PNGs, hash-named). Needed once.
• 2. Pack upscaled (the mandatory step) — converts hd_work/upscaled/*.png into
  hd_pack_hd/<hash>.rgba and refreshes any stale normal maps. Run it after
  every change to the upscaled folder.
• Generate normal maps — builds <hash>_n.rgba files; only needed for Bump.
• Extract 2D UI — dumps Libs/*.LIB interface sprites (2296) for reference.
  They can NOT be re-injected: the game composites its UI itself.
• Show status — extracted / upscaled / packed counts.
• Aspect (on the Play tab, but an HD-mode setting) — the game renders a fixed
  640×480 4:3 frame. "Keep 4:3" pillarboxes it with black bars and correct
  proportions (default); "Stretch to fill" fills the screen, ~33 % wider on
  16:9. The mouse mapping follows both modes, so the cursor stays accurate. In
  Vanilla mode the aspect belongs to dgVoodoo (ScalingMode in dgVoodoo.conf).
• 2D sharpen — sharpens the 2D layer (menus, briefings). 0 = off. This is the
  INCU_SHARP variable read only by our OpenGlide — inert in Original mode.
• Bump strength — fake-relief strength; only affects textures that have a
  <hash>_n.rgba in the pack. 0 = off.
• Bump diagnostic — renders the normal map itself instead of the texture, to
  verify it loaded. Keep OFF for normal play.
• Open source / upscaled / pack — open the three working folders.

STEP BY STEP

  1. "1. Extract textures" (once).
  2. Upscale the PNGs from hd_work/source with any tool you like.
  3. Drop results into hd_work/upscaled (keep the hash prefix; suffixes like
     "_out" are fine).
  4. "2. Pack upscaled".
  5. Play tab → HD mode → Launch.
  6. For an A/B, untick "HD textures" and relaunch.

NOTES

  The pack can be filled gradually — missing textures just render as stock.
  Nothing on this tab touches the game's own files.
