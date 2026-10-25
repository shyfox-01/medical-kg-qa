"""Minimal reader for the first sheet of an .xlsx file, standard library only.

An .xlsx file is a zip of XML parts; rows come from xl/worksheets/sheet1.xml and text
from xl/sharedStrings.xml. Enough for small published datasets (MedicationQA).
"""

import re
import zipfile
from xml.etree import ElementTree

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _column(ref: str) -> int:
    number = 0
    for letter in re.match(r'[A-Z]+', ref).group():
        number = number * 26 + ord(letter) - 64
    return number - 1


def rows(path) -> list[list[str]]:
    with zipfile.ZipFile(path) as book:
        shared = []
        if 'xl/sharedStrings.xml' in book.namelist():
            for item in ElementTree.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si', NS):
                shared.append(''.join(t.text or '' for t in item.iter('{%s}t' % NS['m'])))
        sheet = ElementTree.fromstring(book.read('xl/worksheets/sheet1.xml'))
    table = []
    for row in sheet.iter('{%s}row' % NS['m']):
        values: dict[int, str] = {}
        for cell in row.findall('m:c', NS):
            kind, value = cell.get('t'), cell.find('m:v', NS)
            if kind == 'inlineStr':
                text = ''.join(t.text or '' for t in cell.iter('{%s}t' % NS['m']))
            elif value is None:
                text = ''
            elif kind == 's':
                text = shared[int(value.text)]
            else:
                text = value.text or ''
            values[_column(cell.get('r'))] = text
        table.append([values.get(i, '') for i in range(max(values) + 1)] if values else [])
    return table
