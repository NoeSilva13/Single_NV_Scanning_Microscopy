"""Structural checks on the assembly ConfocalFrame emits.

QICK-DAWG is not installed on the control PC, so the tProc instruction stream
is inspected through recording stubs instead of being compiled.
"""

from rfsoc.confocal_frame import ConfocalFrame

# One tProc output port carries the AOM, the pixel clock and the ADC trigger.
SOCCFG = {
    "tprocs": [{
        "f_time": 430.08,
        "output_pins": {0: ("PMOD0_0", 3, 0), 1: ("PMOD0_1", 3, 1)},
    }],
    "readouts": [{"trigger_port": 3, "trigger_bit": 14, "f_output": 307.2}],
}


def frame_config(width=4, n_lines=3, n_flyback=2, n_lead=2):
    cfg = type("FakeConfig", (), {})()
    cfg.adc_channel = 0
    cfg.laser_gate_pmod = 0
    cfg.pixel_clock_pmod = 1
    cfg.pixel_clock_width_treg = 43
    cfg.pixel_settle_treg = 2150
    cfg.readout_integration_treg = 61440
    cfg.readout_window_tproc_treg = 86016
    cfg.flyback_period_treg = 430080
    cfg.relax_delay_treg = 1
    cfg.reps = width
    cfg.n_lines = n_lines
    cfg.n_flyback = n_flyback
    cfg.n_lead = n_lead
    return cfg


def recorded_program(cfg):
    """Build a ConfocalFrame whose assembly calls are recorded, not compiled."""
    program = ConfocalFrame.__new__(ConfocalFrame)
    program.cfg = cfg
    program.soccfg = SOCCFG
    asm = []

    def record(name, *args, **kwargs):
        asm.append((name, args, kwargs))

    for name in (
        "check_cfg", "setup_readout", "synci", "regwi", "label", "loopnz",
        "mathi", "memwi", "trigger", "trigger_no_off", "append_instruction",
        "wait_all", "sync_all",
    ):
        setattr(program, name, lambda *a, _n=name, **k: record(_n, *a, **k))

    program.make_program()
    return asm


def test_pixel_loop_triggers_the_adc_once_per_pixel():
    asm = recorded_program(frame_config())
    triggers = [call for call in asm if call[0] == "trigger_no_off"]
    adc_triggers = [call for call in triggers if call[2].get("adcs")]
    assert len(adc_triggers) == 1
    assert adc_triggers[0][2]["adcs"] == [0]
    assert adc_triggers[0][2]["t"] == 2150
    # The ADC window is closed by a write that keeps only the AOM bit.
    closing = [
        call for call in triggers
        if call[2].get("t") == 2150 + 86016 and not call[2].get("adcs")
    ]
    assert len(closing) == 1


def test_loops_nest_lines_outside_pixels_with_retrace_between():
    asm = recorded_program(frame_config(width=4, n_lines=3))
    labels = [args[0] for name, args, _kw in asm if name == "label"]
    assert labels == ["LOOP_lead", "LOOP_line", "LOOP_pixel", "LOOP_flyback"]

    jumps = [args[2] for name, args, _kw in asm if name == "loopnz"]
    assert jumps == ["LOOP_lead", "LOOP_pixel", "LOOP_flyback", "LOOP_line"]
    assert asm[-1][0] == "append_instruction"

    counters = {args[1]: args[2] for name, args, _kw in asm if name == "regwi"}
    # 13 is the shot counter, 14 lines, 15 pixels, 17 the shared retrace counter.
    assert counters[13] == 0
    assert counters[14] == 2
    assert counters[15] == 3
    assert counters[17] == 1


def test_shot_counter_advances_once_per_readout():
    asm = recorded_program(frame_config())
    increments = [call for call in asm if call[0] == "mathi"]
    writes = [call for call in asm if call[0] == "memwi"]
    assert len(increments) == len(writes) == 1
    assert writes[0][1][2] == ConfocalFrame.COUNTER_ADDR
    # The counter must be written inside the pixel loop, which is what the QICK
    # streamer uses to address the accumulated buffer.
    pixel_loop = next(
        i for i, (name, args, _kw) in enumerate(asm)
        if name == "loopnz" and args[2] == "LOOP_pixel"
    )
    assert asm.index(writes[0]) < pixel_loop


def test_retrace_clocks_carry_no_readout():
    asm = recorded_program(frame_config(n_flyback=3, n_lead=5))
    lead = asm.index(("label", ("LOOP_lead",), {}))
    line = asm.index(("label", ("LOOP_line",), {}))
    lead_block = asm[lead:line]
    assert not any(call[2].get("adcs") for call in lead_block)
    assert any(
        call[0] == "synci" and call[1] == (430080,) for call in lead_block
    )


def test_expected_readouts_covers_the_whole_block():
    program = ConfocalFrame.__new__(ConfocalFrame)
    program.cfg = frame_config(width=100, n_lines=88)
    assert program.expected_readouts == 8800
