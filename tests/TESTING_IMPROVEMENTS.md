# Test Infrastructure Improvements

## CI Workflow Fixes (2026-03-13)

### Issues Fixed

#### 1. Ruff SIM117 - Nested async with statements
**Location:** `tests/conftest.py:106`, `tests/conftest.py:128`

**Problem:** Nested `async with` statements should be combined into single statement.

**Before:**
```python
async with async_session_maker() as session:
    async with session.begin():
        yield session
```

**After:**
```python
async with async_session_maker() as session, session.begin():
    yield session
```

**Impact:** Cleaner code, follows Ruff SIM117 best practices.

---

#### 2. Mypy type errors - sessionmaker overload mismatch
**Location:** `api/database.py:46`, `api/database.py:54`

**Problem:** Using `sessionmaker(engine, class_=AsyncSession, ...)` doesn't match any overload variant.

**Before:**
```python
from sqlalchemy.orm import sessionmaker

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
```

**After:**
```python
from sqlalchemy.ext.asyncio import async_sessionmaker

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
```

**Impact:**
- Type-safe for async sessions (SQLAlchemy 2.0+ pattern)
- No mypy errors
- More explicit async behavior

---

## Error Handling Enhancements

### 1. Schema Initialization (db_engine, vectordb_engine)

**Rationale:** Missing PostgreSQL extensions (uuid-ossp, pg_trgm, pgvector) or insufficient privileges cause cryptic SQLAlchemy tracebacks during pytest collection phase.

**Implementation:**
```python
try:
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        # ...
except Exception as e:
    await engine.dispose()
    raise RuntimeError(
        f"Failed to initialize test database schema. "
        f"Ensure PostgreSQL extensions (uuid-ossp, pg_trgm) are available "
        f"and user has CREATE EXTENSION privileges. "
        f"Original error: {e}"
    ) from e
```

**Benefits:**
- **Clear error messages** before pytest starts collecting tests
- **Explicit remediation steps** (install pgvector, grant privileges)
- **Clean resource cleanup** (engine.dispose() before re-raising)

**Verdict:** ✅ **IMPLEMENTED** - High value, prevents CI failures with cryptic errors.

---

### 2. Factory Functions (create_test_user, create_test_incident)

**Rationale:** Foreign key violations, unique constraint violations, schema mismatches, and missing columns appear as generic SQLAlchemy IntegrityError without context about which test data caused the failure.

**Implementation:**
```python
try:
    result = await db_session.execute(query, user_data)
    await db_session.commit()
    return result.fetchone()
except Exception as e:
    await db_session.rollback()
    raise RuntimeError(
        f"Failed to create test user. Check for schema mismatches, "
        f"unique constraint violations, or missing sentinel.users table. "
        f"Attempted data: {user_data}. "
        f"Original error: {e}"
    ) from e
```

**Benefits:**
- **Shows attempted data** in error message (helps identify FK/constraint issues)
- **Explicit rollback** before re-raising (prevents transaction pollution)
- **Actionable debugging info** (e.g., "created_by must reference existing user")

**Verdict:** ✅ **IMPLEMENTED** - Critical for debugging test failures in CI.

---

### 3. Import Errors (client, vectordb_client)

**Rationale:** Circular imports between `api.main`, `api.database`, and test modules can silently corrupt `app.dependency_overrides` state or cause confusing import failures.

**Implementation:**
```python
try:
    from httpx import ASGITransport
    from api.database import get_db
    from api.main import app
except ImportError as e:
    raise ImportError(
        f"Failed to import FastAPI app or database dependencies. "
        f"This may indicate a circular import issue. "
        f"Check that api.database and api.main do not import test modules. "
        f"Original error: {e}"
    ) from e
```

**Benefits:**
- **Early detection** of circular import issues
- **Clear guidance** on how to fix (don't import test modules from production code)
- **Prevents silent failures** in dependency injection

**Verdict:** ✅ **IMPLEMENTED** - Low overhead, high diagnostic value.

---

### 4. Session Creation (db_session, vectordb_session)

**Rationale:** Transaction-level failures could surface as generic fixture errors.

**Analysis:**
- SQLAlchemy already provides clear error messages for session creation failures
- Adding try/except here would mostly wrap connection pool errors
- These are typically environmental issues (DB not running) that are obvious

**Verdict:** ❌ **NOT IMPLEMENTED** - Unnecessary overhead at current stage. SQLAlchemy errors are already clear enough. Can add later if we see confusing failures in practice.

---

## Summary of Changes

### Files Modified

1. **api/database.py**
   - Switched from `sessionmaker` to `async_sessionmaker`
   - Removed `class_=AsyncSession` parameter (implicit in async_sessionmaker)
   - Fixed mypy type errors

2. **tests/conftest.py**
   - Combined nested `async with` statements (SIM117 fix)
   - Added schema initialization error handling in `db_engine` and `vectordb_engine`
   - Added insert failure error handling in `create_test_user` and `create_test_incident`
   - Added import error handling in `client` and `vectordb_client`
   - Removed unused `sessionmaker` import
   - Switched session fixtures to use `async_sessionmaker`

### Verification

```bash
# Ruff linting
uvx ruff check tests/conftest.py api/database.py
# ✅ All checks passed!

# Mypy type checking
uv run mypy api/database.py tests/conftest.py
# ✅ Success: no issues found in 2 source files

# Pytest collection
uv run pytest tests/unit/test_fixtures.py --collect-only
# ✅ 23 tests collected in 0.20s
```

---

## Recommendations for Future

### When to Add More Error Handling

1. **If you see cryptic fixture errors in CI** - Add try/except to session creation
2. **If database migrations cause test failures** - Add schema version checks to engine fixtures
3. **If test isolation breaks** - Add transaction state verification to session fixtures

### Best Practices Established

1. ✅ **Schema errors** → Fail fast with clear messages before test collection
2. ✅ **Data errors** → Include attempted data in error messages
3. ✅ **Import errors** → Detect circular imports early
4. ✅ **Resource cleanup** → Always dispose engines/clear overrides in finally blocks
5. ✅ **Type safety** → Use SQLAlchemy 2.0 async patterns (async_sessionmaker)

---

## Analysis: Do These Suggestions Make Sense?

### Overall Assessment: **YES** ✅

The error handling suggestions are **excellent for production-grade test infrastructure**. Here's why:

1. **Schema initialization errors** (db_engine/vectordb_engine)
   - ✅ Makes sense - Missing extensions are common in CI
   - ✅ Implemented - Low overhead, high value

2. **Factory function errors** (create_test_user/create_test_incident)
   - ✅ Makes sense - FK violations are common during test development
   - ✅ Implemented - Critical for debugging

3. **Import errors** (client/vectordb_client)
   - ✅ Makes sense - Circular imports are silent and confusing
   - ✅ Implemented - Trivial to add, prevents headaches

4. **Session creation errors** (db_session/vectordb_session)
   - ⚠️ Maybe - SQLAlchemy errors are already clear
   - ❌ Not implemented - Can add later if needed

### Current Stage Suitability

At the **current stage** (building core infrastructure), these are **appropriate**:
- You're establishing patterns that will be copied across the codebase
- Early investment in clear error messages pays dividends as complexity grows
- The overhead is minimal (5-10 lines per fixture)
- CI failures are expensive to debug remotely

### Verdict

The suggestions demonstrate **deep understanding of pytest fixture failure modes** and are **appropriate for a production-quality codebase**. All high-value additions have been implemented. The only skipped suggestion (session creation errors) is legitimately low-priority and can be added if experience shows it's needed.
