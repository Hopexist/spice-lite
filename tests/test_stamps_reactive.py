"""Stamps for C and L (DC: s = 0, AC: s = j*omega), plus complex source values."""
import numpy as np

from spicelite.circuit import Capacitor, CurrentSource, Inductor, VoltageSource
from spicelite.elements import stamp_capacitor, stamp_current_source, stamp_inductor, stamp_voltage_source


def test_capacitor_ac_is_admittance_sC():
    A = np.zeros((2, 2), dtype=complex)
    stamp_capacitor(A, {"a": 0, "b": 1}, Capacitor("c1", "a", "b", 3.0), 2j)  # y = 6j
    assert np.array_equal(A, [[6j, -6j], [-6j, 6j]])


def test_capacitor_to_ground_stamps_only_diagonal():
    A = np.zeros((1, 1), dtype=complex)
    stamp_capacitor(A, {"a": 0}, Capacitor("c1", "a", "0", 3.0), 2j)
    assert np.array_equal(A, [[6j]])


def test_capacitor_dc_stamps_nothing():
    A = np.zeros((2, 2))
    stamp_capacitor(A, {"a": 0, "b": 1}, Capacitor("c1", "a", "b", 3.0), 0.0)
    assert not A.any()


def test_inductor_ac_branch_row_has_minus_sL():
    A = np.zeros((3, 3), dtype=complex)
    stamp_inductor(A, {"a": 0, "b": 1}, 2, Inductor("l1", "a", "b", 0.5), 4j)  # sL = 2j
    assert np.array_equal(A, [[0, 0, 1], [0, 0, -1], [1, -1, -2j]])


def test_inductor_dc_is_zero_volt_source():
    A = np.zeros((2, 2))
    stamp_inductor(A, {"a": 0}, 1, Inductor("l1", "a", "0", 0.5), 0.0)
    assert np.array_equal(A, [[0, 1], [1, 0]])  # same as a V source to ground; b stays 0


def test_voltage_source_stamp_accepts_complex_value():
    A, b = np.zeros((2, 2), dtype=complex), np.zeros(2, dtype=complex)
    stamp_voltage_source(A, b, {"a": 0}, 1, VoltageSource("v1", "a", "0", 5.0), 1 + 2j)
    assert b[1] == 1 + 2j


def test_current_source_stamp_accepts_complex_value():
    b = np.zeros(1, dtype=complex)
    stamp_current_source(b, {"a": 0}, CurrentSource("i1", "0", "a", 5.0), 2j)
    assert b[0] == 2j
