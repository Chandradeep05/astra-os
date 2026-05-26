# Contributing to ASTRA-OS

First off, thank you for taking the time to contribute! ASTRA-OS is a local-first AI operating runtime built for privacy, safety, and reliability. 

To maintain the high quality and certification standards of the project, please follow these guidelines when contributing.

## 🔬 Test Certification Standard

ASTRA-OS maintains a rigorous **113-Test Certification Suite** covering:
- Route authentication enforcement
- Python execution sandbox isolation
- Ollama runtime lifecycle events
- Folder watcher debounce and soft-delete mechanics
- APScheduler task dispatching
- Observability and audit logging schema consistency
- E2E Playwright tests

> [!IMPORTANT]
> **Any new feature or change must pass 100% of the 113 tests before a Pull Request can be merged.** Run the test suite locally to verify changes.

---

## 🚀 How to Contribute

### 1. Fork and Clone
1. Fork the repository on GitHub.
2. Clone your fork locally:
   ```bash
   git clone https://github.com/your-username/astra-os.git
   cd astra-os
   ```

### 2. Create a Topic Branch
Branch off `main` (or `dev` if specified):
```bash
git checkout -b feature/your-awesome-feature
```

### 3. Setup Local Environment
Follow the installation guide in the `README.md` to spin up:
- The FastAPI backend (port `8000`)
- The Next.js frontend (port `3000`)
- Local Ollama running `qwen2.5:3b` and `nomic-embed-text`

### 4. Implement Changes
- **Keep it local-first**: Never add telemetry, external tracker APIs, or remote integrations without explicit approval.
- **Maintain security boundaries**: If exposing new tool capabilities or OS interaction surfaces, ensure they are gated behind the **Human-in-the-Loop approval gate** in `backend/app/agent/approval.py` or the Python execution sandbox.
- **Do not commit secrets**: Ensure your `.env`, database backups, and local session files do not get added to git. Refer to `.gitignore` to stay compliant.

### 5. Verify & Test
Run the backend tests:
```bash
cd backend
pytest  # Run pytest test suites
```
Verify the frontend build has no TypeScript or compilation errors:
```bash
cd frontend
npm run build
```

### 6. Create a Pull Request
1. Commit your changes with clear, structured messages.
2. Push to your fork:
   ```bash
   git push origin feature/your-awesome-feature
   ```
3. Open a Pull Request on the main repository. Provide a detailed summary of what was added/fixed and link any relevant issues.

---

## 📄 Code Style Guidelines
- **Python**: Follow PEP 8 guidelines. Keep imports organized. Use typed annotations for function inputs and returns wherever possible.
- **TypeScript**: Avoid using `any`. Ensure type-safety. Keep component styling aligned to Tailwind and Framer Motion for responsive design.
- **Audit Logs**: Any new background task or system action must be wired to the audit logger (`task_logger`) and emit consistent schemas to maintain observability integrity.
