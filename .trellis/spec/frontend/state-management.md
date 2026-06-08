# State Management

This document covers state management patterns including URL state with nuqs, React Context guidelines, and synchronization strategies.

## State Categories

| Category | Tool | When to Use |
|----------|------|-------------|
| Server State | React Query | API data, cached responses |
| URL State | nuqs | Filters, pagination, selected items |
| Local UI State | useState | Transient UI (modals, dropdowns) |
| Shared UI State | Context | Cross-component UI state |

## URL State with nuqs

### Why URL State?

- Shareable: Users can share links with specific state
- Bookmarkable: Browser history navigation works
- SEO-friendly: Search engines can index different states
- Persistent: Survives page refreshes

### Basic Usage

```typescript
import { useQueryState } from 'nuqs';

export function useOrderFilters() {
  const [status, setStatus] = useQueryState('status');
  const [page, setPage] = useQueryState('page', {
    parse: (value) => parseInt(value, 10) || 1,
    serialize: String,
  });

  return { status, setStatus, page, setPage };
}
```

### With Default Values

```typescript
import { useQueryState, parseAsInteger, parseAsString } from 'nuqs';

export function useProductFilters() {
  const [category, setCategory] = useQueryState('category', {
    defaultValue: 'all',
    parse: parseAsString,
  });

  const [page, setPage] = useQueryState('page', {
    defaultValue: 1,
    parse: parseAsInteger,
  });

  const [sortBy, setSortBy] = useQueryState('sort', {
    defaultValue: 'newest',
  });

  return {
    category,
    setCategory,
    page,
    setPage,
    sortBy,
    setSortBy,
  };
}
```

### Complex Filter Objects

```typescript
import { useQueryStates, parseAsString, parseAsInteger } from 'nuqs';

const filterParsers = {
  search: parseAsString.withDefault(''),
  category: parseAsString.withDefault('all'),
  minPrice: parseAsInteger,
  maxPrice: parseAsInteger,
  page: parseAsInteger.withDefault(1),
};

export function useAdvancedFilters() {
  const [filters, setFilters] = useQueryStates(filterParsers);

  const updateFilter = <K extends keyof typeof filters>(
    key: K,
    value: (typeof filters)[K]
  ) => {
    setFilters({ [key]: value, page: 1 }); // Reset page on filter change
  };

  const resetFilters = () => {
    setFilters({
      search: '',
      category: 'all',
      minPrice: null,
      maxPrice: null,
      page: 1,
    });
  };

  return { filters, updateFilter, resetFilters };
}
```

### Shallow Routing

Prevent full page reloads when updating URL state:

```typescript
const [tab, setTab] = useQueryState('tab', {
  shallow: true, // Default is true in nuqs
  history: 'push', // or 'replace'
});
```

## React Context Guidelines

### When to Use Context

- Theme/appearance settings
- User preferences
- Feature flags
- Cross-cutting concerns (toast notifications, modals)

### When NOT to Use Context

- Server data (use React Query instead)
- Form state (use form libraries)
- Single-component state (use useState)
- State that should be in URL

### Context Pattern

```typescript
// context/DashboardContext.tsx
import { createContext, useContext, useState, ReactNode } from 'react';

interface DashboardState {
  sidebarCollapsed: boolean;
  activeWidget: string | null;
}

interface DashboardContextValue extends DashboardState {
  toggleSidebar: () => void;
  setActiveWidget: (widget: string | null) => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DashboardState>({
    sidebarCollapsed: false,
    activeWidget: null,
  });

  const toggleSidebar = () => {
    setState((prev) => ({
      ...prev,
      sidebarCollapsed: !prev.sidebarCollapsed,
    }));
  };

  const setActiveWidget = (widget: string | null) => {
    setState((prev) => ({ ...prev, activeWidget: widget }));
  };

  return (
    <DashboardContext.Provider
      value={{ ...state, toggleSidebar, setActiveWidget }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error('useDashboard must be used within DashboardProvider');
  }
  return context;
}
```

### Split Context for Performance

Separate frequently-changing values to prevent unnecessary re-renders:

```typescript
// Separate contexts for state and actions
const DashboardStateContext = createContext<DashboardState | null>(null);
const DashboardActionsContext = createContext<DashboardActions | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DashboardState>(initialState);

  // Memoize actions to prevent re-renders
  const actions = useMemo(
    () => ({
      toggleSidebar: () =>
        setState((prev) => ({
          ...prev,
          sidebarCollapsed: !prev.sidebarCollapsed,
        })),
      setActiveWidget: (widget: string | null) =>
        setState((prev) => ({ ...prev, activeWidget: widget })),
    }),
    []
  );

  return (
    <DashboardStateContext.Provider value={state}>
      <DashboardActionsContext.Provider value={actions}>
        {children}
      </DashboardActionsContext.Provider>
    </DashboardStateContext.Provider>
  );
}

// Separate hooks for state and actions
export function useDashboardState() {
  const context = useContext(DashboardStateContext);
  if (!context) throw new Error('Missing DashboardProvider');
  return context;
}

export function useDashboardActions() {
  const context = useContext(DashboardActionsContext);
  if (!context) throw new Error('Missing DashboardProvider');
  return context;
}
```

## Context and URL Synchronization

When state needs to be both in context (for easy access) and URL (for shareability):

### Pattern: URL as Source of Truth

```typescript
import { useQueryState } from 'nuqs';
import { createContext, useContext, ReactNode } from 'react';

interface FilterContextValue {
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  view: 'grid' | 'list';
  setView: (view: 'grid' | 'list') => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  // URL state as the single source of truth
  const [selectedId, setSelectedId] = useQueryState('selected');
  const [view, setView] = useQueryState('view', {
    defaultValue: 'grid' as const,
    parse: (v) => (v === 'list' ? 'list' : 'grid'),
  });

  return (
    <FilterContext.Provider
      value={{
        selectedId,
        setSelectedId,
        view,
        setView,
      }}
    >
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const context = useContext(FilterContext);
  if (!context) throw new Error('Missing FilterProvider');
  return context;
}
```

### Pattern: Sync Context to URL

When context state needs to be reflected in URL for specific scenarios:

```typescript
export function useSyncToUrl() {
  const { selectedId } = useItemSelection(); // From context
  const [, setUrlSelectedId] = useQueryState('selected');

  // Sync context changes to URL
  useEffect(() => {
    setUrlSelectedId(selectedId);
  }, [selectedId, setUrlSelectedId]);
}
```

### Pattern: Initialize Context from URL

```typescript
export function SelectionProvider({ children }: { children: ReactNode }) {
  // Read initial value from URL
  const [urlSelectedId] = useQueryState('selected');

  const [selectedId, setSelectedId] = useState<string | null>(
    urlSelectedId // Initialize from URL
  );

  // Keep context in sync with URL changes
  useEffect(() => {
    setSelectedId(urlSelectedId);
  }, [urlSelectedId]);

  return (
    <SelectionContext.Provider value={{ selectedId, setSelectedId }}>
      {children}
    </SelectionContext.Provider>
  );
}
```

## Durable UI Snapshots

Use a separate durable snapshot when a UI has both a short-lived rendered view and a longer-lived export/history view. Do not use the visible DOM subset as the source of truth for exportable data.

### Convention: Separate Visible Items From History

**What**: Keep bounded visible state and full history state as separate fields in the domain store, then publish immutable snapshots to React state.

**Why**: Renderers often trim visible items for readability. If export/history reads from the trimmed list, older entries silently disappear and revision metadata can be lost.

**Example**:
```typescript
import { formatPlainTranscript } from './subtitle-export'

interface SubtitleState {
  visible: SubtitleEntry[]
  history: SubtitleEntry[]
}

class SubtitleStore {
  private _visible: SubtitleEntry[] = []
  private _history: SubtitleEntry[] = []

  get visible(): SubtitleEntry[] {
    return this._visible
  }

  get history(): SubtitleEntry[] {
    return this._history
  }

  exportTranscript(): string {
    return formatPlainTranscript(this._history)
  }
}
```

### Convention: Generate Export Artifacts From History On Demand

**What**: Subtitle export artifacts are pure formatting results derived from durable `history`, not long-lived React state fields.

**Why**: Live translation updates can arrive per token. Keeping TXT/SRT/VTT/Markdown strings in React state makes every token update do extra string work and creates another copy of the same data.

**Signatures**:
```typescript
function hasExportableSubtitles(entries: SubtitleEntry[]): boolean
function formatPlainTranscript(entries: SubtitleEntry[]): string
function formatSrtSubtitles(entries: SubtitleEntry[]): string
function formatVttSubtitles(entries: SubtitleEntry[]): string
function formatLearningNotesMarkdown(entries: SubtitleEntry[]): string
```

**Contracts**:
- All export functions read from full subtitle `history`, not the visible subtitle list.
- Empty entries are skipped when both `sourceText` and `translatedText` are blank.
- SRT and VTT timestamps are relative to the first exportable subtitle entry.
- Revised entries include a visible revision marker such as `ASR revised` or `Translation revised`.
- React state may expose `subtitleHistory`; it should not keep precomputed TXT/SRT/VTT/Markdown strings.

**Good/Base/Bad Cases**:
- Good: the history panel calls the formatter only when the user copies or downloads an artifact.
- Base: `SubtitleStore.exportTranscript()` delegates to the same plain-transcript formatter for compatibility.
- Bad: `AppState` stores every export string and regenerates them during every token or revision update.

**Tests Required**:
- Build/type-check the frontend after adding a new export format.
- Verify a trimmed visible list can still export older history entries.
- Verify revised entries keep their revision markers in TXT, SRT, VTT, and Markdown outputs.

**Good/Base/Bad Cases**:
- Good: append every subtitle entry to `history`, derive `visible` from the last N entries, and export from `history`.
- Base: reset both `visible` and `history` when a session stops.
- Bad: export from a renderer-managed DOM node or from a list that is trimmed for display.

**Tests Required**:
- Add or run checks that verify a trimmed visible list still leaves older entries in exported history.
- Verify revision messages update both the displayed entry and the exported transcript metadata.

## State Debugging

### React Query DevTools

```typescript
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

function App() {
  return (
    <>
      <AppContent />
      <ReactQueryDevtools initialIsOpen={false} />
    </>
  );
}
```

### Context Debug Component

```typescript
function DebugContext() {
  const state = useDashboardState();

  if (process.env.NODE_ENV !== 'development') return null;

  return (
    <pre className="fixed bottom-4 right-4 p-2 bg-black/80 text-white text-xs">
      {JSON.stringify(state, null, 2)}
    </pre>
  );
}
```

## Best Practices

1. **URL First**: Default to URL state for shareable data
2. **Minimal Context**: Keep context small and focused
3. **Separate Concerns**: Don't mix server state with UI state
4. **Type Everything**: Use TypeScript for all state types
5. **Default Values**: Always provide sensible defaults
6. **Single Source**: Avoid duplicating state across systems

## Anti-Patterns

- Storing server data in context (use React Query)
- Using context for form state (use form libraries)
- Deep nesting of providers
- Not memoizing context actions
- Duplicating URL state in useState
