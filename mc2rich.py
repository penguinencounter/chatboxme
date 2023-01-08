# Convert Minecraft formatting codes (&a, etc) to rich formmatted text

from rich import print as rp
from rich.markup import escape

from spymap import based

CODES = {
    '0': '[rgb(0,0,0)]',
    '1': '[rgb(0,0,170)]',
    '2': '[rgb(0,170,0)]',
    '3': '[rgb(0,170,170)]',
    '4': '[rgb(170,0,0)]',
    '5': '[rgb(170,0,170)]',
    '6': '[rgb(255,170,0)]',
    '7': '[rgb(170,170,170)]',
    '8': '[rgb(85,85,85)]',
    '9': '[rgb(85,85,255)]',
    'a': '[rgb(85,255,85)]',
    'b': '[rgb(85,255,255)]',
    'c': '[rgb(255,85,85)]',
    'd': '[rgb(255,85,255)]',
    'e': '[rgb(255,255,85)]',
    'f': '[rgb(255,255,255)]',
    'k': '[blink]',
    'l': '[bold]',
    'm': '[strikethrough]',
    'n': '[underline]',
    'o': '[italic]',
    # 'r': '[/blink][/bold][/strikethrough][/underline][/italic][rgb(255,255,255)]',
    'r': '[/][rgb(255,255,255)]',
}


def mc2rich(text: str) -> str:
    """Convert Minecraft formatting codes (&a, etc) to rich formmatted text"""
    text = escape(text)
    for code, rich in CODES.items():
        text = text.replace('&' + code, rich)
    return text


if __name__ == '__main__':
    testbench = """&nMinecraft Formatting&r

&00 &11 &22 &33
&44 &55 &66 &77
&88 &99 &aa &bb
&cc &dd &ee &ff

&rk &kMinecraft
&rl &lMinecraft
&rm &mMinecraft
&rn &nMinecraft
&ro &oMinecraft
&rr &rMinecraft"""
    rp(mc2rich(testbench))

    print()
    rp(mc2rich(based.dbhealth_report()))
