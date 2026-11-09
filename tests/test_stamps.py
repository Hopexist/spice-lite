import numpy as np

from spicelite.circuit import CurrentSource, Resistor, VoltageSource
from spicelite.elements import stamp_current_source, stamp_resistor, stamp_voltage_source


def test_resistor_between_two_nodes():
    A = np.zeros((2, 2))
    stamp_resistor(A, {"a": 0, "b": 1}, Resistor("r1", "a", "b", 2.0))  # g = 0.5
    assert np.array_equal(A, [[0.5, -0.5], [-0.5, 0.5]])


def test_resistor_to_ground_stamps_only_diagonal():
    A = np.zeros((1, 1))
    stamp_resistor(A, {"a": 0}, Resistor("r1", "a", "0", 4.0))
    assert np.array_equal(A, [[0.25]])


def test_resistors_accumulate():
    A = np.zeros((1, 1))
    idx = {"a": 0}
    stamp_resistor(A, idx, Resistor("r1", "a", "0", 4.0))
    stamp_resistor(A, idx, Resistor("r2", "0", "a", 4.0))
    assert np.array_equal(A, [[0.5]])


def test_voltage_source_between_two_nodes():
    A, b = np.zeros((3, 3)), np.zeros(3)
    stamp_voltage_source(A, b, {"a": 0, "b": 1}, 2, VoltageSource("v1", "a", "b", 5.0))
    assert np.array_equal(A, [[0, 0, 1], [0, 0, -1], [1, -1, 0]])
    assert np.array_equal(b, [0, 0, 5])


def test_voltage_source_to_ground():
    A, b = np.zeros((2, 2)), np.zeros(2)
    stamp_voltage_source(A, b, {"a": 0}, 1, VoltageSource("v1", "a", "0", 5.0))
    assert np.array_equal(A, [[0, 1], [1, 0]])
    assert np.array_equal(b, [0, 5])


def test_voltage_source_negative_terminal_on_node():
    # V1 0 a 5 means v(0) - v(a) = 5, i.e. v(a) = -5.
    A, b = np.zeros((2, 2)), np.zeros(2)
    stamp_voltage_source(A, b, {"a": 0}, 1, VoltageSource("v1", "0", "a", 5.0))
    assert np.array_equal(A, [[0, -1], [-1, 0]])
    assert np.array_equal(b, [0, 5])


def test_current_source_injects_into_n_minus():
    b = np.zeros(2)
    stamp_current_source(b, {"a": 0, "b": 1}, CurrentSource("i1", "a", "b", 2e-3))
    assert np.array_equal(b, [-2e-3, 2e-3])


def test_current_source_from_ground():
    b = np.zeros(1)
    stamp_current_source(b, {"a": 0}, CurrentSource("i1", "0", "a", 2e-3))
    assert np.array_equal(b, [2e-3])
