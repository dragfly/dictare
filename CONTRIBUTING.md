# Contributing to dictare

Thank you for your interest in contributing to dictare! This document provides guidelines and instructions for contributing.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/dragfly/dictare.git
   cd dictare
   ```

2. **Install uv** (if not already installed)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Set up the development environment**

   macOS Apple Silicon (with MLX GPU acceleration):
   ```bash
   uv sync --python 3.11 --extra mlx --extra dev
   ```

   macOS Intel / Linux:
   ```bash
   uv sync --python 3.11 --extra dev
   ```

   > **Note**: Python 3.11 is required for MLX/torch compatibility.

4. **Verify the setup**
   ```bash
   uv run dictare check
   ```

## Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=src/dictare --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_state.py
```

## Code Style

We use **ruff** for linting and formatting, and **mypy** for type checking.

```bash
# Check linting
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check . --fix

# Format code
uv run ruff format .

# Type checking
uv run mypy src/
```

## Making Changes

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clear, concise code
   - Add type hints to new functions
   - Follow existing code patterns

3. **Add tests**
   - Add tests for new functionality
   - Ensure existing tests still pass

4. **Update CHANGELOG.md**
   - Add an entry under `[Unreleased]` section
   - Use present tense ("Add feature" not "Added feature")
   - Reference issues/PRs where applicable

5. **Commit your changes**
   - Use clear, descriptive commit messages
   - Follow conventional commits format when possible:
     - `feat:` for new features
     - `fix:` for bug fixes
     - `docs:` for documentation changes
     - `refactor:` for code refactoring
     - `test:` for test changes

## Pull Request Process

1. **Push your branch**
   ```bash
   git push -u origin feature/your-feature-name
   ```

2. **Open a Pull Request**
   - Use a clear, descriptive title
   - Fill out the PR template
   - Reference any related issues

3. **Respond to feedback**
   - Address review comments
   - Push additional commits as needed

4. **Merge**
   - PRs are merged after approval
   - Squash merging is preferred for cleaner history

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Check existing issues before creating a new one
- Use the issue templates when available
- Provide as much context as possible:
  - OS and version
  - Python version
  - Steps to reproduce
  - Expected vs actual behavior

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

- Open an issue for questions about the codebase
- Check existing documentation in `docs/`
- Review `ARCHITECTURE.md` for system design overview

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
