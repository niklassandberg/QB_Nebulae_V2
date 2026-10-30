import nebio

# MCP3208 12-bit ADC. Both chips (CV on spidev0.0, POT on spidev0.1) are
# scanned by nebio (C++); read_adc() returns the code from the current input
# snapshot. The SPI command bytes now live in Code/nebio/src/adc.cpp.

class MCP3208(object):

    def __init__(self, device):
        """device: 0 = CV chip (SPI CE0), 1 = POT chip (SPI CE1)."""
        nebio.inputs()
        self.device = device
        self.base = device * 8
        self.codes = nebio.adc_codes() # filled in place by every snapshot

    def read_adc(self, adc_number):
        """Read the current value of the specified ADC channel (0-7), 0-4095."""
        assert 0 <= adc_number <= 7, 'ADC number must be a value of 0-7!'
        return self.codes[self.base + adc_number]
