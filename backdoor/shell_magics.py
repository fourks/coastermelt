#
# Implementation of IPython "magics", the cute shell-like
# functions you can use in the debugger shell.
#

__all__ = [
    'ShellMagics',
    'd', 'r0', 'r1',
]

from IPython.core import magic
from IPython.core.magic_arguments import magic_arguments, argument, parse_argstring
from IPython.core.display import display

import struct, sys
from hilbert import hilbert

from shell_functions import *
from code import *
from dump import *
from mem import *
from watch import *

# Global Device interface to support magics.
# This can also be used by shell python code, but it shouldn't be used outside the shell.
d = None

# We use r0 and r1 for argument and results in %ea
r0 = None
r1 = None


@magic.magics_class
class ShellMagics(magic.Magics):

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Address to read from. Hexadecimal. Not necessarily aligned')
    @argument('size', type=hexint, nargs='?', default=0x100, help='Number of bytes to read')
    def rd(self, line):
        """Read ARM memory block"""
        args = parse_argstring(self.rd, line)
        dump(d, args.address, args.size)

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Address to read from')
    @argument('wordcount', type=hexint, nargs='?', default=0x100, help='Number of words to read')
    def rdw(self, line):
        """Read ARM memory block, displaying the result as words"""
        args = parse_argstring(self.rdw, line)
        dump_words(d, args.address, args.wordcount)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address')
    @argument('word', type=hexint, nargs='*', help='Hex words')
    def wrf(self, line, cell='', va=0x500000):
        """Write hex words into the RAM overlay region, then instantly move the overlay into place.
           It's a sneaky trick that looks like a temporary way to write to Flash.

           For example, this patches the signature as it appears in the
           current version of the Backdoor patch itself. Normally this can't
           be modified, since it's in flash:

            : rd c9720 50
            000c9720  ac 42 4c 58 ac 6c 6f 63 ac 65 65 42 ac 6f 6b 42   .BLX.loc.eeB.okB
            000c9730  e6 0c 00 02 a8 00 04 04 c0 46 c0 46 c0 46 c0 46   .........F.F.F.F
            000c9740  7e 4d 65 53 60 31 34 20 76 2e 30 32 20 20 20 20   ~MeS`14 v.02    
            000c9750  53 1c 0b 60 16 70 0a 68 53 1c 0b 60 16 70 0a 68   S..`.p.hS..`.p.h
            000c9760  53 1c 0b 60 16 70 0a 68 53 1c 0b 60 16 70 29 88   S..`.p.hS..`.p).

            : wrf c9740 55555555

            : rd c9720 50
            000c9720  ac 42 4c 58 ac 6c 6f 63 ac 65 65 42 ac 6f 6b 42   .BLX.loc.eeB.okB
            000c9730  e6 0c 00 02 a8 00 04 04 c0 46 c0 46 c0 46 c0 46   .........F.F.F.F
            000c9740  55 55 55 55 60 31 34 20 76 2e 30 32 20 20 20 20   UUUU`14 v.02    
            000c9750  53 1c 0b 60 16 70 0a 68 53 1c 0b 60 16 70 0a 68   S..`.p.hS..`.p.h
            000c9760  53 1c 0b 60 16 70 0a 68 53 1c 0b 60 16 70 29 88   S..`.p.hS..`.p).

            : sc c ac
            00000000  55 55 55 55 60 31 34 20 76 2e 30 32               UUUU`14 v.02

           """
        args = parse_argstring(self.wr, line)
        args.word.extend(map(hexint, cell.split()))
        overlay_set(d, va, len(args.word))
        poke_words(d, va, args.word)
        overlay_set(d, args.address, len(args.word))

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address')
    @argument('word', type=hexint, nargs='*', help='Hex words')
    def wr(self, line, cell=''):
        """Write hex words into ARM memory"""
        args = parse_argstring(self.wr, line)
        args.word.extend(map(hexint, cell.split()))
        poke_words(d, args.address, args.word)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address')
    @argument('word', type=hexint, nargs='*', help='Hex words')
    def orr(self, line, cell=''):
        """Read/modify/write hex words into ARM memory, [mem] |= arg"""
        args = parse_argstring(self.orr, line)
        args.word.extend(map(hexint, cell.split()))
        for i, w in enumerate(args.word):
            poke_orr(d, args.address + i*4, w)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address')
    @argument('word', type=hexint, nargs='*', help='Hex words')
    def bic(self, line, cell=''):
        """Read/modify/write hex words into ARM memory, [mem] &= ~arg"""
        args = parse_argstring(self.bic, line)
        args.word.extend(map(hexint, cell.split()))
        for i, w in enumerate(args.word):
            poke_bic(d, args.address + i*4, w)

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address, word aligned')
    @argument('word', type=hexint, help='Hex word')
    @argument('count', type=hexint, help='Hex wordcount')
    def fill(self, line):
        """Fill contiguous words in ARM memory with the same value.

        The current impementation uses many poke()s for a general case,
        but values which can be made of a repeating one-byte pattern
        can be filled orders of magnitude faster by using a Backdoor
        command.
        """
        args = parse_argstring(self.fill, line)
        d.fill(args.address, args.word, args.count)

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint_tuple, nargs='+', help='Single hex address, or a range start:end including both endpoints')
    def watch(self, line):
        """Watch memory for changes, shows the results in an ASCII data table.

        To use the results programmatically, see the watch_scanner() and
        watch_tabulator() functions.

        Keeps running until you kill it with a KeyboardInterrupt.
        """
        args = parse_argstring(self.watch, line)
        changes = watch_scanner(d, args.address)
        try:
            for line in watch_tabulator(changes):
                print line
        except KeyboardInterrupt:
            pass

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, help='First address to search')
    @argument('size', type=hexint, help='Size of region to search')
    @argument('byte', type=hexint, nargs='+', help='List of bytes to search for, at any alignment')
    def find(self, line):
        """Read ARM memory block, and look for all occurrences of a byte sequence"""
        args = parse_argstring(self.find, line)
        substr = ''.join(map(chr, args.byte))
        for address, before, after in search_block(d, args.address, args.size, substr):
            print "%08x %52s [ %s ] %s" % (address, hexstr(before), hexstr(substr), hexstr(after))

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, nargs='?')
    @argument('wordcount', type=hexint, nargs='?', default=1, help='Number of words to remap')
    def ovl(self, line):
        """Position a movable RAM overlay at the indicated virtual address range.
        With no parameters, shows the current location of the RAM.

        It can go anywhere in the first 8MB. So, put it between 20_ and 80_, fill it with
        tasty data, then move it overtop of flash. Or see the wrf / asmf commands to do this
        quickly in one step.
        """
        args = parse_argstring(self.ovl, line)
        if args.address is None:
            print "overlay: base = %x, wordcount = %x" % overlay_get(d)
        else:
            overlay_set(d, args.address, args.wordcount)

    @magic.line_magic
    @magic_arguments()
    @argument('address', type=hexint, help='Hex address')
    @argument('size', type=hexint, nargs='?', default=0x40, help='Hex byte count')
    def dis(self, line):
        """Disassemble ARM instructions"""
        args = parse_argstring(self.dis, line)
        print disassemble(d, args.address, args.size)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('-b', '--base', type=int, default=0, help='First address in map')
    @argument('-s', '--scale', type=int, default=256, help='Scale in bytes per pixel')
    @argument('-w', '--width', type=int, default=4096, help='Size of square hilbert map, in pixels')
    @argument('x', type=int)
    @argument('y', type=int)
    def msl(self, line, cell=''):
        """Memsquare lookup"""
        args = parse_argstring(self.msl, line)
        return int(args.base + args.scale * hilbert(args.x, args.y, args.width))

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint)
    @argument('code', nargs='*')
    def asm(self, line, cell=''):
        """Assemble one or more ARM instructions

        NOTE that the assembled instructions will be padded to the
        nearest 32-bit word. Uses thumb mode by default, but you can
        switch to ARM with the '.arm' directive.

        Use with line or cell mode:

            %asm address op; op; op

            %%asm address
            op
            op
            op
        """
        args = parse_argstring(self.asm, line)
        code = ' '.join(args.code) + '\n' + cell
        try:
            assemble(d, args.address, code, defines=all_defines())
        except CodeError, e:
            usage_error_from_code(e)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('address', type=hexint)
    @argument('code', nargs='*')
    def asmf(self, line, cell='', va=0x500000):
        """Assemble ARM instructions into a patch we instantly overlay onto Flash.
        Combines the 'asm' and 'wrf' commands.
        """
        args = parse_argstring(self.asmf, line)
        code = ' '.join(args.code) + '\n' + cell
        data = assemble_string(args.address, code, defines=all_defines())

        # Write assembled code to the virtual apping
        words = words_from_string(data)
        overlay_set(d, va, len(words))
        poke_words(d, va, words)
        overlay_set(d, args.address, len(words))

    @magic.line_cell_magic
    def ec(self, line, cell='', address=pad+0x100):
        """Evaluate a 32-bit C++ expression on the target"""
        try:
            return evalc(d, line + cell, defines=all_defines(), address=address)
        except CodeError, e:
            usage_error_from_code(e)

    @magic.line_magic
    def ea(self, line, address=pad+0x100):
        """Evaluate an assembly one-liner

        This is an even more reduced and simplified counterpart to %asm,
        like the %ec for assembly.

        - We default to ARM instead of Thumb, since code density is less
          important than having access to all the instructions.

        - Automatically adds a function preamble that saves all registers
          except r0 and r1, which are available for returns.

        - Bridges shell variable r0 on input, and r0-r1 on output.

        - Calls the routine.
        """
        try:
            global r0, r1
            r0, r1 = evalasm(d, line, r0 or 0, defines=all_defines(), address=address)
            print "  r0 = 0x%08x, r1 = 0x%08x" % (r0, r1)
        except CodeError, e:
            usage_error_from_code(e)

    @magic.line_cell_magic
    @magic_arguments()
    @argument('hook_address', type=hexint)
    @argument('handler_address', nargs='?', type=hexint, default=pad+0x100)
    @argument('-q', '--quiet', action='store_true')
    def hook(self, line, cell=None):
        """Use the overlay mapping to install an 8-byte hook that invokes a block of
        compiled C++ code installed in the scratchpad RAM.

        You can use this to install live C++ patches into code that's
        executing directly from flash memory. With some constraints... The
        patch occupies 8 bytes of virtual address space, and control flow may
        only enter the block at the very beginning. The edges of this block
        can't cut any instructions in half.

        Example, counts disc ejects and stores some registers for future
        examination:

            fill _ 0 1_
            fc uint32_t* result = (uint32_t*) (pad + 0xf00)
            ec result[0]

            %%hook 8564c
                result[0]++;
                for (int i = 0; i <= 12; i++)
                    result[1 + i] = regs[i];

        Without any arguments, this uses the hook body "default_hook(regs)"
        which traces register state in the pad, in a format that's easy to
        interact with using %rd, %rdw, and %trace commands.

        Example, visualize invocations of a timer IRQ:

            hook <timer interrupt>
            rd _
            trace _:_3f
        """
        args = parse_argstring(self.hook, line)
        try:
            overlay_hook(d, args.hook_address,
                cell or "default_hook(regs)",
                defines = all_defines(),
                handler_address = args.handler_address,
                verbose = not args.quiet)
        except CodeError, e:
            usage_error_from_code(e)

    @magic.line_cell_magic
    def fc(self, line, cell=None):
        """Define or replace a C++ include definition

        - Without any argument, lists all existing definitions
        - In line mode, stores a one-line function, variable, or structure definition
        - In block mode, stores a multiline function, struct, or class definition

        The key for the includes ditcionary is automatically chosen. In cell mode,
        it's a whitespace-normalized version of the header line. In line mode, it
        extends until the first '{' or '=' character.

        The underlying dictionary is 'includes'. You can remove all includes with:

            includes.clear()

        Example:

            fill _100 1 100
            wr _100 abcdef
            rd _100

            fc uint32_t* words = (uint32_t*) buffer
            buffer = pad + 0x100
            ec words[0]

            %%fc uint32_t sum(uint32_t* values, int count)
            uint32_t result = 0;
            while (count--) {
                result += *(values++);
            }
            return result;

            ec sum(words, 10)

        It's also worth noting that include files are re-read every time you evaluate
        a C++ expression, so a command like this will allow you to edit code in one
        window and interactively run expressions in another:

            fc #include "my_functions.h"

        """
        if cell:
            dict_key = ' '.join(line.split())
            body = "%s {\n%s;\n};\n" % (line, cell)
            includes[dict_key] = body

        elif not line.strip():
            for key, value in includes.items():
                print ' '.join([
                    '=' * 10,
                    key,
                    '=' * max(0, 70 - len(key))
                ])
                print value
                print

        else:
            dict_key = ' '.join(line.split()).split('{')[0].split('=')[0]
            includes[dict_key] = line + ';'

    @magic.line_magic
    @magic_arguments()
    @argument('len', type=hexint, help='Length of input transfer')
    @argument('cdb', type=hexint, nargs='*', help='Up to 12 SCSI CDB bytes')
    def sc(self, line, cell=''):
        """Send a low-level SCSI command with a 12-byte CDB"""
        args = parse_argstring(self.sc, line)
        cdb = ''.join(map(chr, args.cdb))
        data = scsi_in(d, cdb, args.len)
        sys.stdout.write(hexdump(data))

    @magic.line_magic
    def reset(self, line):
        """Reset and reopen the device."""
        d.reset()

    @magic.line_magic
    def eject(self, line):
        """Ask the drive to eject its disc."""
        self.sc('0 1b 0 0 0 2')

    @magic.line_magic
    def sc_sense(self, line):
        """Send a Request Sense command."""
        self.sc('20 3 0 0 0 20')

    @magic.line_magic
    @magic_arguments()
    @argument('lba', type=hexint, help='Logical Block Address')
    @argument('length', type=hexint, nargs='?', default=1, help='Transfer length, in 2kb blocks')
    @argument('-f', type=str, default=None, metavar='FILE', help='Log binary data to a file also')
    def sc_read(self, line, cell=''):
        """Read blocks from the SCSI device."""
        args = parse_argstring(self.sc_read, line)
        cdb = struct.pack('>BBII', 0xA8, 0, args.lba, args.length)
        data = scsi_in(d, cdb, args.length * 2048)
        sys.stdout.write(hexdump(data, log_file=args.f))
