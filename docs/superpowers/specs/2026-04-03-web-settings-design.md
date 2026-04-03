# Web Settings & SSH Key Management — Design Spec

**Date:** 2026-04-03
**Status:** Approved

## Summary

Migrate all `.env` configuration to a web-based Settings page. SSH keys stored in DB (encrypted), not as container files. `.env` remains as fallback. Multiple admin users supported.

## Decisions

- **Architecture:** Key-value `settings` table + separate `ssh_keys` table
- **Encryption:** Fernet (AES-128-CBC) using `SECRET_KEY` from `.env`
- **Infra vars:** `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` stay in `.env` only (chicken-and-egg)
- **Hot reload:** Most settings reload via 60s TTL cache; `aitunnel_base_url`, `aitunnel_api_key`, `tg_bot_token` require restart (banner shown)
- **Users:** Multiple admins, managed via web UI; seed first user from `.env`

---

## 1. Data Models

### Table: `settings`

```sql
CREATE TABLE settings (
    `key`        VARCHAR(128) PRIMARY KEY,
    value        TEXT NOT NULL,
    category     VARCHAR(64) NOT NULL,   -- 'llm', 'telegram', 'ssh', 'schedule'
    is_secret    BOOLEAN DEFAULT FALSE,
    requires_restart BOOLEAN DEFAULT FALSE,
    updated_at   DATETIME DEFAULT NOW() ON UPDATE NOW()
);
```

**Seed records:**

| key | category | is_secret | requires_restart |
|-----|----------|-----------|-----------------|
| `aitunnel_base_url` | llm | no | yes |
| `aitunnel_api_key` | llm | yes | yes |
| `model_main` | llm | no | no |
| `model_fast` | llm | no | no |
| `tg_bot_token` | telegram | yes | yes |
| `tg_chat_id` | telegram | no | no |
| `tg_allowed_users` | telegram | no | no |
| `ssh_default_user` | ssh | no | no |
| `check_interval_minutes` | schedule | no | no |

### Table: `ssh_keys`

```sql
CREATE TABLE ssh_keys (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE,
    private_key TEXT NOT NULL,              -- Fernet encrypted
    is_default  BOOLEAN DEFAULT FALSE,
    created_at  DATETIME DEFAULT NOW(),
    updated_at  DATETIME DEFAULT NOW() ON UPDATE NOW()
);
```

### Table: `servers` — changes

- **Remove:** `ssh_key_path`, `ssh_password`
- **Add:** `ssh_key_id INT FK -> ssh_keys.id NULLABLE` (NULL = use default key)

---

## 2. Settings Service & Caching

### `SettingsService` (app/services/settings.py)

**Read path:**
- In-memory dict cache, reloaded from DB every 60 seconds (TTL)
- Secrets decrypted on read
- Returns typed `AppSettings` Pydantic model
- `get_app_settings() -> AppSettings` — single entry point

**Write path:**
- `update_setting(key, value)` — encrypt if `is_secret`, save, invalidate cache
- `update_settings(updates: dict)` — bulk update for form submission
- Returns `requires_restart: bool` if any changed setting has `requires_restart=True`

**Fallback order:**
1. Value from DB (`settings` table) — if non-empty
2. Value from `.env` (via pydantic-settings `Settings`)
3. Code default

**First startup:** Seed migration writes `.env` values into `settings` table if empty.

### Encryption

- `cryptography.fernet.Fernet` with key derived from `SECRET_KEY`
- `encrypt_value(plain: str) -> str` and `decrypt_value(cipher: str) -> str`
- Applied to `settings` rows where `is_secret=True` and all `ssh_keys.private_key`

### Hot reload vs restart

| Setting | Hot reload | Why |
|---------|-----------|-----|
| `model_main`, `model_fast` | yes | Passed per LLM call |
| `tg_chat_id`, `tg_allowed_users` | yes | Read per message |
| `check_interval_minutes` | yes | Celery Beat reads next tick |
| `ssh_default_user` | yes | Read per connection |
| `aitunnel_base_url`, `aitunnel_api_key` | no (restart) | LLM client init at startup |
| `tg_bot_token` | no (restart) | Bot polling init at startup |

---

## 3. Web Interface

### Navigation

Sidebar: add **"Settings"** (gear icon) between "AI Recommendations" and "Logout".

### Page: `/settings` — tabs by category

**Tab: LLM**
- `aitunnel_base_url` — text input
- `aitunnel_api_key` — password input, masked display (`sk-ait***...xyz`), show/hide toggle
- `model_main` — text input
- `model_fast` — text input

**Tab: Telegram**
- `tg_bot_token` — password input with mask
- `tg_chat_id` — text input
- `tg_allowed_users` — text input (comma-separated)

**Tab: SSH**
- `ssh_default_user` — text input
- **SSH Keys table:** Name | Default (radio) | Created | Actions (Edit/Delete)
- "Add SSH Key" button → modal

**Tab: Schedule**
- `check_interval_minutes` — number input

**Tab: Users**
- Users table: username | is_active | created_at | Actions
- "Add User" — form: username, password, is_active
- "Edit User" — change password, toggle active
- "Delete User" — with confirmation, cannot delete last active user
- Cannot delete/deactivate self

**Save behavior:**
- Each tab has "Save" button
- Changed `requires_restart` settings → yellow banner: "Settings changed, restart required: [list]"
- Hot-reload settings → green toast "Settings saved"

### SSH Key Modal (Add / Edit)

Two input modes (toggle):
- **Paste text** — `<textarea>` for private key content
- **Upload file** — `<input type="file">`, JS reads via `FileReader`, sends content as text

Fields: `name` (required), `is_default` checkbox.

### Server edit page changes (`/servers/{id}/edit`)

- **Remove:** `ssh_key_path`, `ssh_password` fields
- **Add:** SSH Key dropdown from `ssh_keys` table: `[Default key] / key-name / ...`
- If no keys exist → warning: "No SSH key configured. Set up in [Settings → SSH](/settings#ssh)"

### Dashboard alerts

If no SSH keys or critical settings empty (tg_bot_token, aitunnel_api_key) → alert banner with links to Settings tabs.

### Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/settings` | GET | Settings page (all tabs) |
| `/settings` | POST | Save settings (category in form data) |
| `/settings/ssh-keys` | GET | JSON list of keys (for server dropdown) |
| `/settings/ssh-keys` | POST | Create SSH key |
| `/settings/ssh-keys/{id}` | POST | Update SSH key |
| `/settings/ssh-keys/{id}/delete` | POST | Delete SSH key |
| `/settings/users` | GET | JSON list of users |
| `/settings/users` | POST | Create user |
| `/settings/users/{id}` | POST | Update user |
| `/settings/users/{id}/delete` | POST | Delete user |

---

## 4. Authentication Changes

- **Primary:** Check against `admin_users` table (bcrypt hashed passwords)
- **Fallback:** If no users in DB → allow `.env` ADMIN_USERNAME/ADMIN_PASSWORD
- **Seed:** First startup creates user from `.env` credentials
- **Hashing:** `passlib[bcrypt]` — `hash_password()`, `verify_password()`

---

## 5. Migration & Compatibility

### Alembic migration (single)

1. Create `settings` table
2. Create `ssh_keys` table
3. Alter `servers`: add `ssh_key_id FK`, drop `ssh_key_path`, drop `ssh_password`

Note: Seeding (`settings` from `.env`, `admin_users` from `.env`) happens at **application startup**, not in the Alembic migration. Alembic only creates schema; the app's lifespan handler runs seed logic when tables are empty.

### Startup order

```
docker compose up
  → db (MariaDB)
  → alembic upgrade head
  → seed: .env → settings (if empty)
  → seed: .env → admin_users (if empty)
  → app: SettingsService reads DB, fallback .env
  → celery/bot use SettingsService
```

### Backward compatibility

- Existing deploys: `.env` continues as fallback. Upgrade → seed populates DB → works without manual action.
- New deploys: minimal `.env` (DATABASE_URL, REDIS_URL, SECRET_KEY), rest via web panel.
- SSH: servers lose `ssh_key_path` binding. Upload key via UI and reassign. Acceptable — project in development, no production server bindings yet.

### New dependencies

- `cryptography` — Fernet encryption (add explicitly to pyproject.toml)
- `passlib[bcrypt]` — password hashing
