# Python Formatter Integration Plan for InkyPi (No Git Hooks)

## Overview
This plan adds comprehensive Python formatting to the InkyPi project using Black, isort, and GitHub Actions for consistent code style and automated enforcement, **without git hooks** for a simpler setup.

## 🎯 Objectives
- Implement automatic Python code formatting with Black
- Add import sorting with isort
- Configure VS Code for auto-formatting on save
- Add GitHub Actions to enforce formatting before merges
- Maintain project's existing conventions (4-space indentation, UTF-8, etc.)
- **Keep setup simple - no git hooks**

## 📋 Implementation Plan

### Phase 1: Core Configuration Files

#### 1.1 Create `pyproject.toml`
```toml
[tool.black]
line-length = 100
target-version = ['py38', 'py39', 'py310', 'py311']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | venv
  | _build
  | buck-out
  | build
  | dist
)/
'''

[tool.isort]
profile = "black"
line_length = 100
multi_line_output = 3
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true
ensure_newline_before_comments = true
```

### Phase 2: VS Code Integration

#### 2.1 Create `.vscode/settings.json`
```json
{
    "[python]": {
        "editor.defaultFormatter": "ms-python.black-formatter",
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    },
    "black-formatter.args": ["--line-length=100"],
    "isort.args": ["--profile", "black", "--line-length", "100"],
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.flake8Args": ["--max-line-length=100", "--extend-ignore=E203,W503"]
}
```

#### 2.2 Create `.vscode/extensions.json`
```json
{
    "recommendations": [
        "ms-python.black-formatter",
        "ms-python.isort",
        "ms-python.flake8"
    ]
}
```

### Phase 3: GitHub Actions Workflow

#### 3.1 Create `.github/workflows/formatting.yml`
```yaml
name: Code Formatting Check

on:
  push:
    branches: [ main, master, develop ]
  pull_request:
    branches: [ main, master, develop ]

jobs:
  formatting:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
      
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install black isort flake8
        
    - name: Check Black formatting
      run: black --check --line-length 100 .
      
    - name: Check isort formatting
      run: isort --check-only --profile black --line-length 100 .
      
    - name: Run flake8
      run: flake8 --max-line-length=100 --extend-ignore=E203,W503 .
```

### Phase 4: Documentation Updates

#### 4.1 Update `AGENTS.md`
Add new section under Code Quality:
```markdown
### Code Quality Tools
```bash
# Format code with Black
black .

# Sort imports with isort
isort .

# Lint with flake8
flake8 .

# Run all formatting tools
black --line-length 100 . && isort --profile black --line-length 100 . && flake8 --max-line-length=100 --extend-ignore=E203,W503 .
```

### Phase 5: Initial Codebase Formatting

#### 5.1 One-time formatting
```bash
# Install tools
pip install black isort flake8

# Format entire codebase
black --line-length 100 .
isort --profile black --line-length 100 .

# Fix any remaining issues
flake8 --max-line-length=100 --extend-ignore=E203,W503 .
```

## 🔄 Migration Strategy

### Impact Analysis
- **High Impact**: Import reorganization (currently inconsistent)
- **Medium Impact**: Line length changes (current max ~141 chars → 100 chars)
- **Low Impact**: Code formatting (already follows 4-space indentation)

### Rollout Plan
1. **Setup Phase**: Add configuration files (no code changes)
2. **Testing Phase**: Run against current codebase, identify conflicts
3. **Formatting Phase**: Apply automatic formatting to entire codebase
4. **Integration Phase**: Enable CI checks and VS Code settings
5. **Documentation Phase**: Update development documentation

## 🛠 Required Extensions

### VS Code Extensions
- **Black Formatter** (`ms-python.black-formatter`) - Official Microsoft Black extension
- **isort** (`ms-python.isort`) - Import sorting
- **Flake8** (`ms-python.flake8`) - Linting (optional but recommended)

### Installation Commands
```bash
# Install VS Code extensions
code --install-extension ms-python.black-formatter
code --install-extension ms-python.isort
code --install-extension ms-python.flake8
```

## 📊 Expected Benefits

1. **Consistency**: Automatic, deterministic formatting across all Python files
2. **Productivity**: Auto-format on save eliminates manual formatting
3. **Quality**: CI checks prevent poorly formatted code from merging
4. **Collaboration**: Standardized style reduces code review discussions
5. **Simplicity**: No git hooks = easier onboarding and maintenance

## ⚠️ Potential Challenges

1. **Initial Formatting**: Large-scale reformatting may affect git history
2. **Line Length**: Some existing code will need reformatting
3. **Import Style**: Significant changes to current import organization
4. **Developer Adoption**: Team members need to install extensions

## 🚀 Implementation Timeline

| Phase | Duration | Priority |
|-------|----------|----------|
| Configuration Files | 1 day | High |
| VS Code Setup | 0.5 day | High |
| GitHub Actions | 0.5 day | High |
| Code Formatting | 1 day | Medium |
| Documentation | 0.5 day | Low |

## 📝 Developer Workflow

**Without Git Hooks:**
1. Developer edits code → VS Code auto-formats on save
2. Developer commits and pushes
3. GitHub Actions checks formatting
4. If fails → PR is blocked → developer fixes locally

**Benefits of this approach:**
- ✅ Fewer moving parts
- ✅ No local setup beyond VS Code extensions  
- ✅ CI enforces standards for all contributors
- ✅ Simpler onboarding for new developers
- ✅ Works with any editor (CI is the ultimate authority)

## 📋 Next Steps

Once approved, the implementation will proceed in phases, with Phase 1-3 being the minimum viable setup for immediate formatting enforcement. The initial codebase formatting (Phase 5) should be done in a separate commit to make the changes easily reviewable.

This simplified approach provides 95% of the benefit with 50% of the setup complexity.