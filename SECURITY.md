# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

---

## Reporting a Vulnerability

We take the security of **Telegram AI Agent Userbot** very seriously. If you discover a security vulnerability or potential privacy leak, please do **NOT** open a public issue.

Instead, please report it privately:
- By emailing the project maintainers or creating a private GitHub Security Advisory.
- Include a detailed description of the vulnerability, steps to reproduce, and any proof-of-concept scripts or logs.

We will acknowledge receipt within 48 hours and work with you to analyze and patch the issue before any public disclosure.

---

## Security Architecture & Defenses

1. **Credential & Secret Protection:**
   - Secrets (`TELEGRAM_API_HASH`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `TELEGRAM_SESSION_STRING`) are modeled as `SecretStr` in Pydantic. They are masked as `**********` in string representations, logs, and exception tracebacks.
   - The `.env` file and session files (`*.session`, `*.session-journal`) are strictly ignored by `.gitignore`.

2. **System Account & Phishing Protection:**
   - `SystemFilter` unconditionally drops messages originating from Telegram official service accounts (e.g. `777000`, `Telegram`, `42777`) and prevents auto-replying to login codes or verification notices.
   - `BotFilter` drops messages from other bots (`is_bot=True` or `*bot` username suffix) to eliminate bot loops and exploitation.

3. **Structural Financial & Credential Interception:**
   - `SensitiveFilter` implements:
     - **Luhn Algorithm Validation**: Detects 13-19 digit credit and debit cards across Latin and Eastern numerals.
     - **OTP & Verification Codes**: Detects 4-8 digit one-time passcodes and login tokens.
     - **Private Keys & API Tokens**: Intercepts RSA/EC private keys and cloud API tokens (`sk-...`, `AIzaSy...`).
   - Intercepted sensitive messages halt auto-replies immediately and dispatch an alert to the user's **Saved Messages**.

4. **Alert Anti-Flood Throttling:**
   - To prevent an attacker from flooding the user's Saved Messages with security alerts, `AlertService` throttles alerts per sender (e.g. 60-second cooldown) and compresses consecutive notices with a counter.

5. **Prompt Injection Defense:**
   - All external, untrusted user messages and quoted contexts sent to LLMs are wrapped in structural XML tags: `<untrusted_user_input>` and `<quoted_context>`.
   - System prompts include strict directives instructing LLMs never to execute system instructions or override rules found within these tags.

6. **PII Redaction Before Cloud Inference:**
   - When `REDACT_PII_BEFORE_LLM=true`, credit cards, OTP codes, and private keys are masked before prompts leave the local host for third-party LLM providers.
