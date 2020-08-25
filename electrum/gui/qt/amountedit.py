# -*- coding: utf-8 -*-

from decimal import Decimal
from typing import Union

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPalette, QPainter
from PyQt5.QtWidgets import (QLineEdit, QStyle, QStyleOptionFrame)

from .util import char_width_in_lineedit, ColorScheme

from electrum.util import (format_satoshis_plain, decimal_point_to_base_unit_name,
                           FEERATE_PRECISION, quantize_feerate)

from qsdn import Locale as QSDNLocale
from qsdn import LimitingNumericValidator as QSDNLimitedNumericValidator 
from PyQt5.QtGui import QValidator
class FreezableLineEdit(QLineEdit):
    frozen = pyqtSignal()

    def setFrozen(self, b):
        self.setReadOnly(b)
        self.setFrame(not b)
        self.frozen.emit()

class AmountEdit(FreezableLineEdit):
    shortcut = pyqtSignal()

    def __init__(self, base_unit, is_int=False, parent=None):
        QLineEdit.__init__(self, parent)
        # This seems sufficient for hundred-BTC amounts with 8 decimals
        self.setFixedWidth(16 * char_width_in_lineedit())
        self.base_unit = base_unit
        #self.textChanged.connect(self.numbify)
        self.is_int = is_int
        self.is_shortcut = False
        self.extra_precision = 0
        self.locale = QSDNLocale()
        add_ws = False
        self.validators = [QSDNLimitedNumericValidator(16, 0, add_ws), None, QSDNLimitedNumericValidator(14, 2, add_ws), None, None, \
            QSDNLimitedNumericValidator(11, 5, add_ws), None, None, QSDNLimitedNumericValidator(8, 8, add_ws)]
        for v in self.validators:
            if v is not None:
                v.bang.connect(self._emit_shortcut)
        self.setValidator(self.validators[self.decimal_point()])

    def _emit_shortcut(self):
    	self.shortcut.emit()


    def decimal_point(self):
        return 8

    def max_precision(self):
        return self.decimal_point() + self.extra_precision

    def numbify(self):
        text = self.text().strip()
        if text == '!':
            self.shortcut.emit()
            return
        chars = '0123456789'
        if not self.is_int: chars +='.'
        s = ''.join([i for i in text if i in chars])
        if not self.is_int:
            if '.' in s:
                p = s.find('.')
                s = s.replace('.','')
                s = s[:p] + '.' + s[p:p+self.max_precision()]
        status, new_s, pos = self.validator.validate(s, self.cursorPosition())
        if status == QValidator.Acceptable:
        	pass
        s = new_s
        self.setText(new_s)
        # setText sets Modified to False.  Instead we want to remember
        # if updates were because of user modification.
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def paintEvent(self, event):
        QLineEdit.paintEvent(self, event)
        if self.base_unit:
        	# must call this here because there is self.decimal_point is simply assigned 
        	# another method instead of changing a value in a way that emits a signal.
            self.setValidator(self.validators[self.decimal_point()])
            panel = QStyleOptionFrame()
            self.initStyleOption(panel)
            textRect = self.style().subElementRect(QStyle.SE_LineEditContents, panel, self)
            textRect.adjust(2, 0, -10, 0)
            painter = QPainter(self)
            painter.setPen(ColorScheme.GRAY.as_color())
            painter.drawText(textRect, Qt.AlignRight | Qt.AlignVCenter, self.base_unit())

    def get_amount(self) -> Union[None, Decimal, int]:
        x, even_a_number = self.locale.toDecimal(self.text())
        if not even_a_number:
        	return None

    def setAmount(self, x):
    	x = self.locale.toString(x)
    	self.setText(x)


class BTCAmountEdit(AmountEdit):

    def __init__(self, decimal_point, is_int=False, parent=None):
        AmountEdit.__init__(self, self._base_unit, is_int, parent)
        self.decimal_point = decimal_point

    def _base_unit(self):
        return decimal_point_to_base_unit_name(self.decimal_point())

	# Returns the amount. 
	# The amount will be in BTC, mBTC, mcBTC or Satoshis depending on the value
	# of self.decimal_point() (which is our units factor)
    def get_amount(self):
        x, even_a_number = self.locale.toDecimal(self.text())
        if not even_a_number:
        	return None
        # scale it to max allowed precision, make it an int
        power = pow(10, self.max_precision())
        max_prec_amount = int(power * x)
        # if the max precision is simply what unit conversion allows, just return
        if self.max_precision() == self.decimal_point():
            return max_prec_amount
        # otherwise, scale it back to the expected unit
        amount = Decimal(max_prec_amount) / pow(10, self.max_precision()-self.decimal_point())
        return Decimal(amount) if not self.is_int else int(amount)


	# sets the amount where /amount_sat/ is in Satoshis
    def setAmount(self, amount_sat):
        if amount_sat is None:
            self.setText(" ") # Space forces repaint in case units changed
        else:
            self.setText(self.locale.toString(Decimal(format_satoshis_plain(amount_sat, self.decimal_point()))))
        self.repaint()  # macOS hack for #6269


class FeerateEdit(BTCAmountEdit):

    def __init__(self, decimal_point, is_int=False, parent=None):
        super().__init__(decimal_point, is_int, parent)
        self.extra_precision = FEERATE_PRECISION

    def _base_unit(self):
        return 'sat/byte'

    def get_amount(self):
        sat_per_byte_amount = BTCAmountEdit.get_amount(self)
        return quantize_feerate(sat_per_byte_amount)

    def setAmount(self, amount):
        amount = quantize_feerate(amount)
        super().setAmount(amount)
