package events

import (
	"context"
	"errors"
)

var ErrQueueFull = errors.New("execution queue is full")

type Consumer interface {
	Consume(ctx context.Context) error
}

type CapacityChecker interface {
	IsFull() bool
}

type BackpressureAwareConsumer struct {
	consumer Consumer
	queue    CapacityChecker
}

func NewBackpressureAwareConsumer(
	consumer Consumer,
	queue CapacityChecker,
) *BackpressureAwareConsumer {
	return &BackpressureAwareConsumer{
		consumer: consumer,
		queue:    queue,
	}
}

func (c *BackpressureAwareConsumer) Consume(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	if c.queue != nil && c.queue.IsFull() {
		return ErrQueueFull
	}

	if c.consumer == nil {
		return nil
	}

	return c.consumer.Consume(ctx)
}

func (c *BackpressureAwareConsumer) IsFull() bool {
	if c.queue == nil {
		return false
	}
	return c.queue.IsFull()
}
