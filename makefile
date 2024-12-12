ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

.PHONY: test
test:
	@poetry run pytest tests

.PHONY: clean
clean:
	@find . -name "*.pyc" -exec rm -f {} \;
	@find . -name "__pycache__" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".pytest_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".mypy_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".ruff_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".DS_Store" -exec rm -f {} \; 2> /dev/null
	@find . -type d -empty -delete

.PHONY: install
install:
	@rm -f poetry.lock
	@poetry install --with dev
	@poetry export --without-hashes -f requirements.txt -o requirements.txt

.PHONY: pypi
pypi:
	@echo "reseting to latest remote..."
	@git pull && git reset --hard origin/main
	@echo "re-installing package..."
	@make install
	@echo "starting PyPI bump process..."
	# check if the new VERSION is provided
	@if [ -z "$$VERSION" ]; then \
	    echo "no VERSION provided, auto-incrementing patch version..."; \
	    OLD_VERSION=$$(poetry version | awk '{print $$2}'); \
	    MAJOR=$$(echo $$OLD_VERSION | cut -d. -f1); \
	    MINOR=$$(echo $$OLD_VERSION | cut -d. -f2); \
	    PATCH=$$(echo $$OLD_VERSION | cut -d. -f3); \
	    NEW_VERSION=$$MAJOR.$$MINOR.$$((PATCH + 1)); \
	    echo "auto-incremented version to $$NEW_VERSION"; \
	    poetry version $$NEW_VERSION; \
		VERSION=$$NEW_VERSION; \
	else \
	    echo "updating version to $$VERSION..."; \
	    poetry version $$VERSION; \
	fi
	# now, publish to PyPi
	@echo "publishing package to PyPI..."
	@if poetry publish --build; then \
		git add pyproject.toml poetry.lock requirements.txt; \
		git commit -m "bump pypi to version $$VERSION"; \
		git push; \
	    echo "package published successfully"; \
	else \
	    echo "failed to publish package"; \
	    exit 1; \
	fi
