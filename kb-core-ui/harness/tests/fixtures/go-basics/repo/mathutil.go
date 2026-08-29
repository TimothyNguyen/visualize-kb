package mathutil

// DefaultStart is the calculator's starting total.
const DefaultStart = 0

// Add returns the sum of two integers.
func Add(a, b int) int {
	return a + b
}

// Adder is implemented by anything that can add.
type Adder interface {
	AddTo(n int) int
}

// Calculator accumulates a running total.
type Calculator struct {
	Total int
}

// AddTo adds n to the calculator's total and returns the new total.
func (c *Calculator) AddTo(n int) int {
	c.Total = Add(c.Total, n)
	return c.Total
}
