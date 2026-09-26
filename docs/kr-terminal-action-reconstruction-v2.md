# KR terminal-action reconstruction v2 — real document pass

This is a data-foundation repair on Draft PR #158, not an Alpha study. No returns, labels, fitted models or backtests are computed; sealed Alpha v1/v2/v3 and production Alpha are unchanged. Do not merge or create v4.

## Verified evidence

- Current input snapshot: `signal-history` commit `4c6813c4cc8e84a9e429b37435e78baba7f1ee78`.
- Original document collection commit: `71c5128a01a7528536a8ff24c4e82d896363fec0`.
- Original dividend collection commit: `dfeb098e26ff71d3b8149199677417a78eda42d6`.
- 22 securities; 451 disclosure-index rows; 6,150 dividend-section rows.
- 130 document receipts attempted: 92 retrieved and parsed, 38 failed. All 92 decoded members round-trip to their recorded original SHA-256. All successful filings were read before failure materiality was classified.
- Parsed 22,193 table rows. `docs/results/kr-terminal-document-parsing.json` identifies every parsed receipt, original member/ZIP hash and its use.
- Dividend amount lineage remains READY for 15/22. Dividend event-date lineage remains BLOCKED for 22/22; no ex-dates invented. This pass does not create dividend events or add terminal cash to the dividend book, preserving the existing amount-lineage deduplication safeguards.

## What is and is not established

Every resolved economic field cites a retained filing, receipt date, original member hash and quotation. The book uses the existing `KR_TERMINAL_CORPORATE_ACTIONS_V1` contract, with its existing component and amendment structures. An additive `CASH_SHARE_EXCHANGE` action type distinguishes cash-instead-of-stock exchanges from tender offers and mergers. No mixed cash-plus-stock or multiple paid successor legs were established for these 22 public-share exits; existing component support remains tested. Fractional-share cash is not classified as an additional fixed cash leg.

**The retained documents establish disclosed contractual terms, not completed payment for every exit.** Fields that are READY below are supported by the selected filed decision. A scheduled effective date is kept distinct from publication date and from execution confirmation. Where a later body correction is missing, its predecessor’s cash/ratio/date remains only in `documentedTerms`; those canonical final fields stay empty and BLOCKED. `finalTermsReceiptNumber` remains empty for all 22; `latestReviewedTermsReceiptNumber` is not relabeled as final. Every action chain remains BLOCKED pending execution/finality evidence. Full reconstruction is therefore 0/22, not 20/22.

Additional known limits: the identity bridge uses exact legal/historical names (legal suffix/spacing normalization only) or an explicit KRX code in a document; ambiguous old/new issuer names and unverified abbreviations stay BLOCKED. It does not fuzzy-match a successor. The identity snapshot is retrospective evidence of identity, not a claim that that mapping was available at the historical event date.

## Counts

| Field | READY / 22 |
|---|---|
| TERMINATION_TYPE | 20 |
| TERMINAL_CONSIDERATION (documented base entitlement) | 10 |
| SUCCESSOR_IDENTITY | 11 |
| EXCHANGE_RATIO | 8 |
| EFFECTIVE_DATE (disclosed schedule) | 11 |
| TERMINAL_ACTION_CHAIN | 0 |
| AMENDMENT_CHAIN (reviewed collected sequence) | 10 |
| DIVIDEND_AMOUNT_LINEAGE | 15 |
| DIVIDEND_EVENT_DATE_LINEAGE | 0 |
| RAW_EVIDENCE | 22 |

Partial records: 20; unresolved parent actions: 2; fully reconstructed: 0. Material failed body corrections block 9 securities. Foundation status: **PARTIALLY_REPAIRED**.

## Per-security documented terms and exact blockers

The entitlement column reports what the cited decision says, including candidates blocked by later unavailable corrections. It is not a claim that the scheduled transaction completed on those terms. Original filing quotes, receipt links and per-field hashes are in the normalized book and completeness JSON.

| Security | Latest reviewed receipt | Documented entitlement per old common share | Disclosed date | Remaining blockers |
|---|---|---|---|---|
| 000030.KS 우리은행 | 20180619000302 | 1.0000000 shares of 우리금융지주 | 2019-01-11 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20180920000544,20181108000137,20181121000025); SUCCESSOR_SECURITY_IDENTITY: AMBIGUOUS_EXACT_IDENTITY; AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 000060.KS 메리츠화재 | 20221205000271 | 1.2657378 shares of 메리츠금융지주 | 2023-02-01 | FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 000830.KS 삼성물산 | 20150526800025 | 0.3500885 shares of 제일모직 | 2015-09-01 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20150608000391,20150612000428,20150619000462); SUCCESSOR_SECURITY_IDENTITY: AMBIGUOUS_EXACT_IDENTITY; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 001300.KS 제일모직 | 20140331800112 | 0.4425482 shares of 삼성SDI | 2014-07-01 | FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 002550.KS KB손해보험 | 20170414002322 | 0.5728700 shares of KB금융지주 | 2017-07-03 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20170516000224,20170530000327); SUCCESSOR_SECURITY_IDENTITY: NO_EXACT_IDENTITY_BRIDGE; FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 003410.KS 쌍용C&E | 20240423000168 | KRW 7,000 cash | 2024-06-25 | AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 003450.KS 현대증권 | 20160802000289 | 0.1907312 shares of KB금융지주 | 2016-11-09 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20160901000273); SUCCESSOR_SECURITY_IDENTITY: NO_EXACT_IDENTITY_BRIDGE; FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 003600.KS SK | 20150420800024 | 0.7367839 shares of 에스케이씨앤씨 | 2015-08-01 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20150430001586,20150513003281,20150521000438,20150528000580,20150528000709); EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 004940.KS 외환은행 | 20130128800003 | 0.1894302 shares of 하나금융지주 | 2013-04-05 | EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 008560.KS 메리츠증권 | 20221205000275 | 0.1607327 shares of 메리츠금융지주 | 2023-04-05 | FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 010520.KS 현대하이스코 | 20150408800141 | 0.8577607 shares of 현대제철 | 2015-07-01 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20150417000066,20150417800108,20150429000977); FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 010620.KS HD현대미포 | 20250827000428 | 0.4059146 shares of HD현대중공업 | 2025-12-01 | FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 011160.KS 두산건설 | 20191212000291 | 0.2480895 shares of 두산중공업 | 2020-03-10 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20191224000172); FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 012510.KS 더존비즈온 | 20260519000237 | KRW 120,000 cash | 2026-06-30 | EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 037620.KS 미래에셋증권 | 20160513004518 | 2.9716317 shares of 미래에셋대우 | 2016-11-01 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20160919000325); AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 042670.KS HD현대인프라코어 | 20250711000213 | 0.1621707 shares of 에이치디현대건설기계 | 2026-01-01 | SUCCESSOR_SECURITY_IDENTITY: NO_EXACT_IDENTITY_BRIDGE; FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 053000.KS 우리금융 | 20140911000016 | 1.0000000 shares of 우리은행 | 2014-11-01 | EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 057050.KS 현대홈쇼핑 | 20260522000254 | 6.3571040 shares of 현대지에프홀딩스 | 2026-06-30 | EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 067250.KS STX조선해양 | — | Not established | — | Only a subsidiary STX France SA / STX France Cabins SAS merger was retrieved; no parent-share terminal terms. |
| 079440.KS 오렌지라이프 | 20191114002655 | 0.6601483 shares of 신한금융지주회사 | 2020-01-28 | FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (20191119000180,20191204000479); SUCCESSOR_SECURITY_IDENTITY: NO_EXACT_IDENTITY_BRIDGE; FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision; EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 115390.KS 락앤락 | 20240830002126 | KRW 8,750 cash | 2024-11-22 | EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment |
| 117930.KS 한진해운 | — | Not established | — | Retrieved filings transfer businesses/assets. Corporate sale proceeds do not establish a per-share liquidation distribution; no terminal shareholder payout is evidenced. |

## Failed receipt triage

| Class | Receipts |
|---|---|
| MATERIALLY_BLOCKING | 21 |
| POTENTIALLY_MATERIAL | 12 |
| REDUNDANT_SUPERSEDED_OR_UNNECESSARY | 5 |

All 38 retained failures say the response was not a ZIP (147 bytes). The original response body was not retained; this is not evidence of a particular DART error code, retry policy or permission problem. No blanket retry was run.

- 21 materially blocking body corrections affect 우리은행, 삼성물산(000830), KB손해보험, 현대증권, SK(003600), 현대하이스코, 두산건설, 미래에셋증권(037620), 오렌지라이프. The exact receipt numbers appear in each record. Other successful filings in the same set were checked: foreign ADS delisting notices, tender results and unrelated subsequent mergers do not prove the missing final exchange/merger terms.
- 12 potentially material receipts comprise unavailable changed attachments and four 한진해운 business-transfer amendments. Asset-sale proceeds are not a shareholder liquidation distribution; no zero recovery is assigned.
- Five unnecessary/superseded receipts: two SK subsidiary-split amendments; the later 현대증권/KB투자증권 merger amendment (현대증권 survives, so this is not its public-share exit); two 더존비즈온 correction/attachment items followed by the retained 2026-05-19 decision restating cash and date.
- No retained alternative proves the exact missing final terms for the materially blocking cases. STX조선해양 only has a foreign-subsidiary merger in this corpus; 한진해운 only has business/asset transfers. Their parent termination type, date and shareholder recovery remain unresolved.

## Amendment and successor discipline

The review file names the selected same-event publication sequence. Each amendment retains its own receipt date, stated original submission date when present, correction-table previews and hashes, and the preceding reviewed version. Later amendments are never backdated to the original filing. Missing attachments/body corrections keep sequence finality BLOCKED. All other raw document receipts remain linked but are not silently inserted into that terminal sequence.

The successor graph uses the existing multi-component contract. True cycles are rejected on book load; a converging diamond is not a cycle. The actual 053000 → 000030 linkage is retained and cannot become a completed chain while the descendant’s final terms remain unresolved.

## Reproduce without a new GitHub Action

Use a checkout of the cited signal-history snapshot, plus its `ledger/dart-ownership-events/collection-universe.json`:

```bash
python scripts/reconstruct_kr_terminal_documents.py --evidence-root /path/to/signal-history --identity-universe /path/to/collection-universe.json
python scripts/build_kr_terminal_action_reconstruction_v2.py --signal-history-root /path/to/signal-history --signal-history-commit 4c6813c4cc8e84a9e429b37435e78baba7f1ee78 --survivorship-audit docs/results/alpha-opportunity-model-v3-survivorship-audit.json --output docs/results/kr-terminal-action-reconstruction-v2.json
```

No GitHub Action is needed to reproduce or validate this parsing pass. Completing the foundation requires additional primary evidence: materially missing amendments, authoritative exact successor identity bridges, fractional treatment where absent, completion/final payment evidence, and separately dividend event-date evidence. A blind rerun of the existing collector is not a demonstrated remedy for the 147-byte non-ZIP responses. No Alpha or replay Action is required.

## Determinism and hashes

The ledger, parsing report and completeness artifact were each rebuilt twice from the same verified inputs; the paired outputs were byte-identical. Sidecar files store their SHA-256.

| Artifact | SHA-256 |
|---|---|
| `data/kr-terminal-corporate-actions.json` | `0ceabddd616859b838537cda8a308efdf013e5a1c8022deb92b6e85413708581` |
| `docs/results/kr-terminal-document-parsing.json` | `df41ffa10d2e8eb49f37c89b0f3b8fe460040b1479cbcdd8e2237f7815a833c8` |
| `docs/results/kr-terminal-action-reconstruction-v2.json` | `a0caf4a9a29a86b50f91d369bfe7a4958e337e45216289feba736e4c0b19d998` |

Source SHA-256 values:

- `dividend-fetch-state.json`: `8d58f1fef9971ad86ec458581d8e48ab97208be4aa8f52d77a068afd66879e82`
- `document-fetch-state.json`: `1f0509b19aa061cb7a1580e38cc662e49602230c2bb8d6222122b56fb6fc1fcf`
- `fetch-state.json`: `73ba4187a80f92a5641ea6e738a919f2dfe365648da97c87a6890d209a55abde`
- `kr-corporate-actions-disclosures.jsonl.gz`: `67436598c0eea5cc209d6b5a93fc64cb472b682aa66e6a143ffc5ff853fab9db`
- `kr-dividend-sections.jsonl.gz`: `9e0f7680b74812f855a3a12e5c2b547cc7e1911e5d9078afe987c64265ed3199`
- `kr-terminal-action-documents.jsonl.gz`: `98c1475f888cb07b5c8865b8902516e463bd934281d1f4744a7aba4b4d687071`

## Validation

- Focused parser, ledger, completeness, dividend and sealed-foundation guardrail tests: 120 passed.
- Full `pytest -q`: 2,313 passed, 1 skipped, 40 existing SciPy deprecation warnings (75.17 seconds).
- `ruff check .`, `python -m compileall pipeline scripts`, `git diff --check` and `assert_pushable`: passed.
- No Codex review/auto-review was invoked; PR stays draft and unmerged.
