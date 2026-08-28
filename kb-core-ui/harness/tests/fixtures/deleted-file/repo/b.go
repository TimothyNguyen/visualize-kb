package multi

// B calls A and adds one.
func B() int {
	return A() + 1
}
