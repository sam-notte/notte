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
