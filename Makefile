SHELL := /bin/bash
ROOT ?= $(HOME)/aws
TOOLS := $(ROOT)/.tools/bin
DOCKER_TOOLS := /Applications/Docker.app/Contents/Resources/bin
PY := .venv/bin/python
AWS := $(TOOLS)/aws
CDK := $(TOOLS)/cdk
PROFILE ?= default
REGION ?= eu-west-2

export AWS_PROFILE := $(PROFILE)
export AWS_REGION := $(REGION)
export AWS_DEFAULT_REGION := $(REGION)
export AWS_CONFIG_FILE := $(ROOT)/.aws/config
export AWS_SHARED_CREDENTIALS_FILE := $(ROOT)/.aws/credentials
export JSII_RUNTIME_PACKAGE_CACHE_ROOT := $(ROOT)/.tools/jsii-cache

.PHONY: test synth whoami login bootstrap deploy destroy outputs smoke

test:
	$(PY) -m unittest discover -s tests

synth:
	PATH="$(TOOLS):$(DOCKER_TOOLS):$$PATH" $(CDK) synth

whoami:
	$(AWS) sts get-caller-identity --profile $(PROFILE) --region $(REGION)

login:
	$(AWS) sso login --profile $(PROFILE)

bootstrap:
	PATH="$(TOOLS):$(DOCKER_TOOLS):$$PATH" $(CDK) bootstrap aws://$$($(AWS) sts get-caller-identity --query Account --output text --profile $(PROFILE))/$(REGION) --profile $(PROFILE)

deploy:
	PATH="$(TOOLS):$(DOCKER_TOOLS):$$PATH" $(CDK) deploy --profile $(PROFILE) --require-approval never

destroy:
	PATH="$(TOOLS):$(DOCKER_TOOLS):$$PATH" $(CDK) destroy --profile $(PROFILE) --force

outputs:
	$(AWS) cloudformation describe-stacks --stack-name RocaCloudStack --profile $(PROFILE) --region $(REGION) --query "Stacks[0].Outputs" --output table

smoke:
	scripts/smoke-roca-cloud.sh
