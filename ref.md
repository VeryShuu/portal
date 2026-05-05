# Code Review — Corporate Intranet Portal

Дата ревью: 2026-05-03  
Последнее обновление: 2026-05-05 (сессии 1–13; закрыто ~74 находки, осталось 2)  
Скоуп: глубокий ревью backend FastAPI + frontend Vue 3 + infra.

Маркировка тяжести:
- **[CRIT]** — безопасность/целостность данных, требует немедленной правки.
- **[HIGH]** — серьёзная проблема (производительность, корректность), требует приоритета.
- **[MED]** — улучшение качества/надёжности.
- **[LOW]** — стилистика, мелочи, документация.

---

## 6. База данных и миграции

### 6.1 [MED] Нумерация миграций линейная (001..035), без branch'ей
- При большом релизе трудно мерджить параллельные ветки.

---

## 5. Архитектура и общие проблемы

### 5.4 [LOW] Большие frontend-компоненты — отложено, анализ проведён

Компоненты исследованы, структура и кандидаты на вынос зафиксированы.

#### `FilesPage.vue` (1039 строк, 27 KB) — наибольший приоритет

Три чётко выделяемых зоны:

1. **`FilesImagePreview.vue`** — image overlay в `<Teleport to="body">` (~50 строк шаблона).  
   Props: `images: NCItem[]`, `initialIndex: number`, `folderId: string`.  
   Emits: `close`. Вся навигация (prev/next, Escape, ArrowLeft/Right) инкапсулируется внутри — keydown-listener переезжает в компонент. Нет зависимостей от родительского state.

2. **`FilesFolderCreateModal.vue`** — модал создания папки (~25 строк шаблона).  
   Props: `show`, `loading`.  
   Emits: `update:show`, `submit(name, description, parentId)`.  
   Вся валидация и форма внутри; `createParentId` передаётся через props.

3. **`FilesPermissionsModal.vue`** — модал управления правами (~60 строк шаблона + логика поиска субъектов).  
   Наиболее сложный к выносу: тянет `subjectSearchQuery`, `subjectSearchResults`, `grantForm`, `permColumns`, `NDataTable` с render-функцией. Имеет смысл выносить вместе с логикой поиска субъектов (`onSubjectSearchChange`, `onSubjectSelect`, debounce-таймер).

#### `NewsFormPage.vue` (835 строк, 25 KB)

Кандидаты:
- **`NewsCoverUpload.vue`** — блок загрузки обложки с focal point (preview + `cover_focal_point` selector).
- **`NewsTargetingForm.vue`** — блок таргетирования (departments/roles multi-select).
- Остальное — плотно связанная форма с TipTap редактором; дробление создаст больше prop drilling, чем пользы.

#### `KbListPage.vue` (748 строк, 22 KB)

Кандидат: **`KbArticleList.vue`** — список статей с пагинацией и фильтрами (правая панель). Левая панель (`KbSectionTree`) уже вынесена. Разбиение снизит файл до ~350 строк.

#### `GlobalSearch.vue` (631 строка, 20 KB)

Кандидаты:
- **`GlobalSearchResultGroup.vue`** — группа результатов (заголовок + список + кнопка «все»), используется 4 раза (news, kb, files, users). Сейчас дублируется через v-for + условные блоки.
- Основная логика (debounce, query, keyboard navigation) остаётся в родителе.

#### Вывод

Разбиение не несёт рисков для бизнес-логики, но требует аккуратного prop/emit-дизайна. Рекомендуемая очерёдность: `FilesImagePreview` (самодостаточна) → `GlobalSearchResultGroup` (устраняет дублирование) → `KbArticleList` → модальные окна FilesPage.

---

**Итого открытых находок**: 2 пункта.  
**Средней важности (открытых)**: 1 (6.1).  
**Низкой / стилистика (открытых)**: 1 (5.4 — отложено).
