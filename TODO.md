# TODO — Prioritised Tracker

Combined, prioritised list of bugs (`B#`, see `BUGS.md`) and improvements
(`I#`, see `IMPROVEMENTS.md`), ordered by severity / potential impact.

Priority key:
- **P0** — data integrity: can log wrong/duplicate/missing time to JIRA, or crash a run.
- **P1** — correctness/portability blockers for anyone setting up or reusing the tool.
- **P2** — robustness, UX, and maintainability.
- **P3** — cleanups and cosmetics.

---

## P0 — Fix first (wrong data reaches JIRA)

- [x] **B1** Malformed CSV row duplicates the previous row's worklog (and crashes on a bad first row). — `build_data`
- [x] **B3** Times before 01:00 produce a negative, invalid hour. — `create_datetime`
- [x] **B2** Hours/minutes not zero-padded in the JIRA timestamp. — `create_datetime`
- [x] **B4** Timezone conversion is a hardcoded "subtract one hour" hack (wrong half the year / outside UK). — `create_datetime`

> B2–B4 are best fixed together via a proper `zoneinfo` datetime conversion (**I2** timezone config).

## P1 — Setup & portability

- [x] **I1** Installation script (`install.sh`). — *delivered in this change*
- [ ] **B13** README instructions don't produce a working command (name mismatch + wrong script path). — resolved in practice by I1; update README prose to match.
- [ ] **B5** `.env` loaded relative to CWD, not the project — config silently becomes `None`. — `load_dotenv`
- [ ] **B6 / I2** JIRA base URL (and timezone) hardcoded; move to `.env`.
- [ ] **B8** No handling when the input file is missing — raw traceback. — `find_file` / `build_data`

## P2 — Robustness, UX, tests

- [x] **B7** CSV opened `'r+'` instead of `'r'`. — `build_data`
- [ ] **I5** HTTP timeout + retries + session reuse. — `log_time`
- [ ] **I7** Expand test coverage (would have caught B1–B3). — `tests/`
- [x] **I6 / B9** Structured skip/error reporting instead of bare `except: pass`.
- [ ] **B10 / I11** Safer cancel/confirmation prompt (case-insensitive, safe default).
- [ ] **I3** Argparse for the file path (usable as `logtime "<path>"`).
- [ ] **I4** Console-script entry point in `pyproject.toml`.
- [x] **I10** Run-summary output (totals per day / per run, success/fail counts).

## P3 — Cleanups & cosmetics

- [x] **B11** Reorder `create_report` checks so the type check precedes `<= 0`.
- [x] **B12** `build_data` return type hint says `-> None` but returns a list.
- [ ] **I8** Prune dependencies (`dotenv` shim, unused `requests-auth`).
- [ ] **I9** Replace `print` with the `logging` module.
- [ ] **I12** Remove dead/commented code; finish truncated docstrings.
- [ ] **I13** Fix `.env.example` `DOWNLOAD_DIR` guidance (WSL mounts at `/mnt/c/...`).

---

### Suggested first sprint
`B1` → `B2`/`B3`/`B4` (+`I2` timezone) → `B5`/`B6` → keep `install.sh` (`I1`) and align the
README (`B13`). That removes every known path to logging incorrect time and makes a fresh
install reliable.
