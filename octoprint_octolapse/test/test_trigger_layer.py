import unittest
from tempfile import NamedTemporaryFile

from octoprint_octolapse.extruder import ExtruderTriggers, ExtruderState
from octoprint_octolapse.position import Position
from octoprint_octolapse.settings import OctolapseSettings
from octoprint_octolapse.trigger import LayerTrigger


class Test_LayerTrigger(unittest.TestCase):
    def setUp(self):
        self.Settings = OctolapseSettings(NamedTemporaryFile().name)
        self.Settings.CurrentPrinter().e_axis_default_mode = 'relative'
        self.Settings.CurrentPrinter().xyz_axes_default_mode = 'absolute'
        self.Settings.CurrentPrinter().auto_detect_position = False
        self.Settings.CurrentPrinter().origin_x = 0
        self.Settings.CurrentPrinter().origin_y = 0
        self.Settings.CurrentPrinter().origin_z = 0
        self.OctoprintPrinterProfile = self.CreateOctoprintPrinterProfile()

    def tearDown(self):
        del self.Settings
        del self.OctoprintPrinterProfile

    def CreateOctoprintPrinterProfile(self):
        return dict(
            volume=dict(
                width=250,
                depth=200,
                height=200,
                formFactor="Not A Circle",
                custom_box=False,
            )
        )

    def TestReset(self):
        """Test the reset function"""
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        trigger = LayerTrigger(self.Settings)
        # test initial state
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # set the flags to different valuse
        trigger.is_triggered = True
        trigger.is_waiting = True
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # test the reset state
        trigger.Reset()
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_LayerChange(self):
        """Test the layer trigger for layer changes triggers"""

        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        trigger = LayerTrigger(self.Settings)
        trigger.ExtruderTriggers = ExtruderTriggers(None, None, None, None, None, None, None, None, None,
                                                    None)  # Ignore extruder
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = 0  # Trigger on any height change
        # test initial state
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # send commands that normally would trigger a layer change, but without all axis homed.
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Home all axis and try again
        position.update("g28")
        trigger.update(position)
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # extrude again on the same layer and make sure it does NOT trigger
        position.update("g0 x1 y1 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # move to higher layer, but do not extrude (no layer change)
        position.update("g0 x1 y1 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # return to previous layer, do not extrude
        position.update("g0 x2 y2 z.2")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x4 y4 z.2")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # extrude again on current layer
        position.update("g0 x2 y2 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # move up two times, down and extrude (this should trigger after the final command
        position.update("g0 x2 y2 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.6")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.4 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # This should never happen in a print, but test extruding on previous layers
        # move down to previous layer, extrude,
        position.update("g0 x2 y2 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # move back to current layer (.4), extrude (no trigger)
        position.update("g0 x2 y2 z.4 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # move up one more layer and extrude (trigger)
        position.update("g0 x2 y2 z.6 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_LayerChange_DefaultExtruderTriggers(self):
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        currentSnapshot = self.Settings.CurrentSnapshot()
        trigger = LayerTrigger(self.Settings)
        trigger.ExtruderTriggers = ExtruderTriggers(
            False, True, True, False, None, None, True, True, None, False)
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = 0  # Trigger on any height change
        # create some gcode
        gcode = []
        # get the startup gcode
        gcode.extend(self.GetPrintStartGcode())
        # start layer 1
        gcode.append(('G1 Z0.250 F7200.000', False, ""))
        # start priming extruder
        gcode.append(('G1 X50.0 E80.0  F1000.0', False,
                      "ExtrudingStart"))  # forbidden
        gcode.append(('G1 X160.0 E20.0 F1000.0', True, "Extruding"))
        gcode.append(('G1 Z0.200 F7200.000', False, "Extruding"))
        gcode.append(('G1 X220.0 E13 F1000.0', False, "Extruding"))
        gcode.append(('G1 X240.0 E0 F1000.0', False, "Extruding"))
        # Object print is starting
        gcode.append(('G1 E-4.00000 F3000.00000', False,
                      "On Retracting, OnRetractingStart"))
        gcode.append(('G1 Z0.700 F7200.000', False, "FullyRetracted, Zhop"))
        gcode.append(('G1 X117.061 Y98.921 F7200.000',
                      False, "FullyRetracted, Zhop"))
        gcode.append(('G1 Z0.200 F7200.000', False, "FullyRetracted"))
        gcode.append(('G1 E4.00000 F3000.00000', False,
                      "DetractingStart, Detracted"))
        gcode.append(('M204 S1000', False, "Primed"))
        gcode.append(('G1 F1800', False, "Primed"))
        # start extruding
        gcode.append(('G1 X117.508 Y98.104 E0.02922',
                      False, "ExtrudingStart"))  # forbidden
        gcode.append(('G1 X117.947 Y97.636 E0.02011', False, "Extruding"))
        gcode.append(('G1 X118.472 Y97.267 E0.02011', False, "Extruding"))
        gcode.append(('G1 X119.061 Y97.013 E0.02011', False, "Extruding"))
        gcode.append(('G1 X119.690 Y96.884 E0.02011', False, "Extruding"))
        gcode.append(('G1 X130.004 Y96.869 E0.32341', False, "Extruding"))
        gcode.append(('G1 X131.079 Y97.061 E0.03423', False, "Extruding"))
        # Retraction
        gcode.append(('G1 E-2.40000 F3000.00000', False,
                      "RetractingStart, Retracting, PartiallyRetracted"))
        gcode.append(('G1 F5760', False, "Retracting, PartiallyRetracted"))
        gcode.append(('G1 X119.824 Y97.629 E-0.50464', False,
                      "Retracting, PartiallyRetracted"))
        gcode.append(('G1 F5760', False, "Retracting, PartiallyRetracted"))
        gcode.append(('G1 X121.876 Y97.628 E-1.01536', False,
                      "Retracting, PartiallyRetracted"))
        gcode.append(('G1 E-0.08000 F3000.00000', False,
                      "Retracting, Fully Retracted"))
        # Retracted, Zhop
        gcode.append(('G1 Z0.700 F7200.000', False, "FullyRetracted, Zhop"))
        # Moved while lifted
        gcode.append(('G1 X120.587 Y100.587 F7200.000',
                      False, "FullyRetracted, Zhop"))
        gcode.append(('G1 Z0.200 F7200.000', False, "FullyRetracted"))
        # Zhop complete
        gcode.append(('G1 E4.00000 F3000.00000', False,
                      "DetractingStart, Detracted"))
        # Retraction Complete
        gcode.append(('G1 F1800', False, "Primed"))  # primed
        gcode.append(('G1 X129.413 Y100.587 E0.27673',
                      False, "ExtrudingStart"))
        gcode.append(('G1 X129.413 Y109.413 E0.27673', False, "Extruding"))
        gcode.append(('G1 X120.587 Y109.413 E0.27673', False, "Extruding"))
        gcode.append(('G1 X120.587 Y100.647 E0.27485', False, "Extruding"))
        gcode.append(('G1 X120.210 Y100.210 F7200.000', False, "Extruding"))

        # layer 2
        # after layer change
        # retract
        gcode.append(('G1 E-4.00000 F3000.00000', False, "RetractingStart"))
        # zhop
        gcode.append(('G1 Z0.900 F7200.000', False, "FullyRetracted, Zhop"))
        # move while lifted
        gcode.append(('G1 X133.089 Y99.490 F7200.000',
                      False, "FullyRetracted, Zhop"))
        # end zhop
        gcode.append(('G1 Z0.400 F7200.000', False, "FullyRetracted"))
        # detract
        gcode.append(('G1 E4.00000 F3000.00000', False, "DetractingStart"))
        gcode.append(('G1 F3000', False, "Detracted, Primed"))
        # start etruding
        gcode.append(('G1 X133.128 Y110.149 E0.33418',
                      False, "ExtrudingStart"))
        gcode.append(('G1 X132.942 Y111.071 E0.02950', True, "Extruding"))
        gcode.append(('G1 X132.492 Y111.896 E0.02950', False, "Extruding"))
        gcode.append(('G1 X132.020 Y112.393 E0.02148', False, "Extruding"))
        gcode.append(('G1 X131.447 Y112.777 E0.02161', False, "Extruding"))

        # layer 3
        gcode.append(('G1 Z2.600 F7200.000', False, "Primed"))
        gcode.append(('G1 X120.632 Y100.632 F7200.000', False, "Primed"))
        gcode.append(('M204 S800', False, "Primed"))
        gcode.append(('G1 F1200', False, "Primed"))
        gcode.append(('G1 X129.368 Y100.632 E0.29570',
                      False, "ExtrudingStart"))
        gcode.append(('G1 X129.368 Y109.368 E0.29570', True, "Extruding"))
        gcode.append(('G1 X120.632 Y109.368 E0.29570', False, "Extruding"))
        gcode.append(('G1 X120.632 Y100.692 E0.29367', False, "Extruding"))
        gcode.append(('M204 S1000', False, "Primed"))
        gcode.append(('G1 X120.225 Y100.225 F7200.000', False, "Extruding"))
        gcode.append(('M204 S800', False, "Primed"))
        gcode.append(('G1 F1200', False, "Extruding"))
        gcode.append(('G1 X129.775 Y100.225 E0.32326', False, "Extruding"))

        # layer 4
        gcode.append(('G1 Z2.800 F7200.000', False, "Primed"))
        gcode.append(('G1 X120.632 Y109.368 F7200.000', False, "Primed"))
        gcode.append(('M204 S800', False, "Primed"))
        gcode.append(('G1 F1200', False, "Primed"))
        gcode.append(('G1 X120.632 Y100.632 E0.29570',
                      False, "ExtrudingStart"))
        gcode.append(('G1 X129.368 Y100.632 E0.29570', True, "Extruding"))
        gcode.append(('G1 X129.368 Y109.368 E0.29570', False, "Extruding"))
        gcode.append(('G1 X120.692 Y109.368 E0.29367', False, "Extruding"))
        gcode.append(('M204 S1000', False, "Primed"))
        gcode.append(('G1 X120.225 Y109.775 F7200.000', False, ""))
        gcode.append(('M204 S800', False, "Primed"))
        gcode.append(('G1 F1200', False, "Primed"))
        gcode.append(('G1 X120.225 Y100.225 E0.32326',
                      False, "ExtrudingStart"))
        gcode.append(('G1 X129.775 Y100.225 E0.32326', False, "Extruding"))
        gcode.append(('G1 X129.775 Y109.775 E0.32326', False, "Extruding"))
        gcode.append(('G1 X120.285 Y109.775 E0.32123', False, "Extruding"))

        # loop through all of the Gcode and test triggering
        for command in gcode:
            gcodeCommand = command[0]
            shouldTrigger = command[1]
            comment = command[2]
            position.update(gcodeCommand)
            trigger.update(position)
            self.assertTrue(trigger.is_triggered(0) == shouldTrigger,
                            "Should have triggered on {0} command.  Command comment:".format(gcodeCommand, comment))

    def GetPrintStartGcode(self):
        # create gcode list
        gcode = []
        # Print Start Code
        gcode.append(('T0', False, "select tool 0"))
        gcode.append(('M104 S255', False, "set extruder temp"))
        gcode.append(('M140 S100', False, "set bed temp"))
        gcode.append(('M190 S100', False, "wait for bed temp"))
        gcode.append(('M109 S255', False, "wait for extruder temp"))
        gcode.append(('G21', False, "set units to millimeters"))
        gcode.append(('G90', False, "use absolute coordinates"))
        gcode.append(('M83', False, "use relative distances for extrusion"))
        gcode.append(('G28 W', False, ""))
        gcode.append(('G80', False, ""))
        gcode.append(('G92 E0.0', False, ""))
        gcode.append(('M203 E100', False, ""))
        gcode.append(('M92 E140', False, ""))
        gcode.append(('G92 E0.0', False, ""))
        gcode.append(('M900 K200', False, ""))

        return gcode

    def test_LayerTrigger_HeightChange(self):
        """Test the layer trigger height change """

        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        trigger = LayerTrigger(self.Settings)
        trigger.ExtruderTriggers = ExtruderTriggers(None, None, None, None, None, None, None, None, None,
                                                    None)  # Ignore extruder
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = .25  # Trigger every .25

        # test initial state
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # send commands that normally would trigger a layer change, but without all axis homed.
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.25
        position.update("g28")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # extrude at height 0.2, should trigger
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.25
        # move to higher layer, but do not extrude (no layer change)
        position.update("g0 x1 y1 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.25
        # return to previous layer, do not extrude
        position.update("g0 x2 y2 z.2")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x4 y4 z.2")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.25
        # extrude again on current layer
        position.update("g0 x2 y2 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.25
        # move up two times, down and extrude (this should trigger after the final command
        position.update("g0 x2 y2 z.4")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.6")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        position.update("g0 x2 y2 z.4 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # cur increment 0.5
        # This should never happen in a print, but test extruding on previous layers
        # move down to previous layer, extrude,
        position.update("g0 x2 y2 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # move back to current layer (.4), extrude (no trigger)
        position.update("g0 x2 y2 z.4 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # move up one more layer and extrude (trigger)
        position.update("g0 x2 y2 z.6 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # test very close to height increment (.74)
        # move up one more layer and extrude (trigger)
        position.update("g0 x2 y2 z0.74  e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))
        # now it should trigger
        position.update("m114")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Test at the increment (.75)
        position.update("g0 x2 y2 z0.7500 e1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_ExtruderTriggers_NotHomed(self):
        """Make sure nothing triggers when the axis aren't homed"""
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        trigger = LayerTrigger(self.Settings)
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = 0  # Trigger on every layer change
        position.Extruder.PrinterRetractionLength = 4

        # Try on extruding start
        trigger.ExtruderTriggers = ExtruderTriggers(
            True, None, None, None, None, None, None, None, None, None)
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on extruding
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, True, None, None, None, None, None, None, None, None)
        position.update("g0 x0 y0 z.3 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on primed
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, True, None, None, None, None, None, None, None)
        position.update("g0 x0 y0 z.4 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on retracting start
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, True, None, None, None, None, None, None)
        position.update("g0 x0 y0 z.5 e-1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on retracting
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, True, None, None, None, None, None)
        position.update("g0 x0 y0 z.5 e-1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on partially retracted
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, True, None, None, None, None)
        position.update("g0 x0 y0 z.5 e-1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on retracted
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, True, None, None, None)
        position.update("g0 x0 y0 z.5 e-1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # try out on detracting
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, True, None, None, None)
        position.update("g0 x0 y0 z.5 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_ExtruderTriggers(self):
        """Test All Extruder Triggers"""
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        # home the axis
        position.update("G28")
        trigger = LayerTrigger(self.Settings)
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = 0  # Trigger on every layer change

        # get the current extruder state
        state = position.Extruder.GetState(0)
        # Try on extruding start right after home, should fail since we haven't extruded yet
        trigger.ExtruderTriggers = ExtruderTriggers(
            True, None, None, None, None, None, None, None, None, None)
        state.IsExtrudingStart = True
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Try again, should trigger after the extrusion
        position.update("G1 E1")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False

        # try out on extruding
        state.IsExtruding = True
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, True, None, None, None, None, None, None, None, None)

        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False

        # try out on primed
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, True, None, None, None, None, None, None, None)
        state.IsPrimed = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False

        # try out on retracting start
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, True, None, None, None, None, None, None)
        state.IsRetractingStart = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False

        # try out on retracting
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, True, None, None, None, None, None)
        state.IsRetracting = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False
        # try out on partially retracted
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, True, None, None, None, None)
        state.IsPartiallyRetracted = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False
        # try out on retracted
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, True, None, None, None)
        state.IsRetracted = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False
        # try out on detracting Start
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, None, True, None, None)
        state.IsDetractingStart = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False
        # try out on detracting Start
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, None, None, True, None)
        state.IsDetracting = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Reset the previous extruder state
        state = ExtruderState()
        position.Extruder.StateHistory[0] = state
        state.IsPrimed = False
        trigger.ExtruderTriggers = ExtruderTriggers(
            None, None, None, None, None, None, None, None, None, True)
        state.IsDetracted = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_ExtruderTriggerWait(self):
        """Test wait on extruder"""
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)

        trigger = LayerTrigger(self.Settings)
        trigger.RequireZHop = False  # no zhop required
        trigger.HeightIncrement = 0  # Trigger on every layer change

        # home the axis
        position.update("G28")

        # add the current state
        pos = position.get_position(0)
        state = position.Extruder.GetState(0)
        state.IsPrimed = False
        # Use on extruding start for this test.
        trigger.ExtruderTriggers = ExtruderTriggers(
            True, None, None, None, None, None, None, None, None, None)
        state.IsExtrudingStart = False
        pos.IsLayerChange = True

        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # update again with no change
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))
        # set the trigger and try again
        state.IsExtrudingStart = True
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

    def test_LayerTrigger_LayerChange_ZHop(self):
        """Test the layer trigger for layer changes triggers"""
        self.Settings.CurrentSnapshot().layer_trigger_require_zhop = True
        self.Settings.CurrentPrinter().z_hop = .5
        position = Position(self.Settings, self.OctoprintPrinterProfile, False)
        trigger = LayerTrigger(self.Settings)
        trigger.ExtruderTriggers = ExtruderTriggers(None, None, None, None, None, None, None, None, None,
                                                    None)  # Ignore extruder
        trigger.HeightIncrement = 0  # Trigger on any height change
        # test initial state
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # send commands that normally would trigger a layer change, but without all axis homed.
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Home all axis and try again, will not trigger or wait, previous axis not homed
        position.update("g28")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # Waiting on ZHop
        position.update("g0 x0 y0 z.2 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))
        # try zhop
        position.update("g0 x0 y0 z.7 ")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # extrude on current layer, no trigger (wait on zhop)
        position.update("g0 x0 y0 z.7 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # do not extrude on current layer, still waiting
        position.update("g0 x0 y0 z.7 ")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # partial hop, but close enough based on our printer measurement tolerance (0.005)
        position.update("g0 x0 y0 z1.1999")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))

        # creat wait state
        position.update("g0 x0 y0 z1.3 e1")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # move down (should never happen, should behave properly anyway)
        position.update("g0 x0 y0 z.8")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # move back up to current layer (should NOT trigger zhop)
        position.update("g0 x0 y0 z1.3")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # move up a bit, not enough to trigger zhop
        position.update("g0 x0 y0 z1.795")
        trigger.update(position)
        self.assertFalse(trigger.is_triggered(0))
        self.assertTrue(trigger.is_waiting(0))

        # move up a bit, just enough to trigger zhop
        position.update("g0 x0 y0 z1.7951")
        trigger.update(position)
        self.assertTrue(trigger.is_triggered(0))
        self.assertFalse(trigger.is_waiting(0))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(Test_LayerTrigger)
    unittest.TextTestRunner(verbosity=3).run(suite)
