.PHONY: all fmt vet test-unit test-unit-race test-integration test-all build clean

all: fmt vet test-unit

fmt:
	gofmt -s -w .

vet:
	go vet ./...

test-unit:
	go test -v -count=1 ./...

test-unit-race:
	go test -v -race -count=1 ./...

test-integration:
	go test -v -count=1 -tags=integration ./...

test-all:
	go test -v -count=1 -tags=integration ./...

build:
	go build -o bin/recovery-executor main.go

clean:
	rm -rf bin/
