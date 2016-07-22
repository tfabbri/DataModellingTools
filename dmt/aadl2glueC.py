#!/usr/bin/env python3
# vim: set expandtab ts=8 sts=4 shiftwidth=4
#
# (C) Semantix Information Technologies.
#
# Semantix Information Technologies is licensing the code of the
# Data Modelling Tools (DMT) in the following dual-license mode:
#
# Commercial Developer License:
#       The DMT Commercial Developer License is the suggested version
# to use for the development of proprietary and/or commercial software.
# This version is for developers/companies who do not want to comply
# with the terms of the GNU Lesser General Public License version 2.1.
#
# GNU LGPL v. 2.1:
#       This version of DMT is the one to use for the development of
# applications, when you are willing to comply with the terms of the
# GNU Lesser General Public License version 2.1.
#
# Note that in both cases, there are no charges (royalties) for the
# generated code.
#
'''
Code Integrator

This is the core of the "glue" generators that Semantix developed for
the European research project ASSERT. It has been enhanced in the
context of Data Modelling and Data Modelling Tuning projects,
and continuous to evolve over the course of other projects.

This code starts by reading the AADL specification of the system.
It then generates the runtime bridge-code that will map the message
data structures from those generated by the Semantix Certified ASN.1
compiler to/from those generated by the modeling tool used to
functionally model the APLC subsystem (e.g. SCADE, ObjectGeode,
Matlab/Simulink, C, Ada, etc).

The code generation is done via user-visible (and editable) backends.

There are three kinds of backends:

1. Synchronous backends
=======================

For these, the working logic is:

for each subprogram implementation
    Load B mapper
    call OnStartup
    for each subprogram param
        Call OnBasic/OnSequence/OnEnumerated etc
    call OnShutdown

That is, there is OnStartup/OnInteger/OnSequence/.../OnShutdown cycle
done PER EACH SUBPROGRAM.

2. Asynchronous backends
========================

Asynchronous backends are only generating standalone encoders and decoders
(they are not doing this per sp.param).

The working logic is therefore different

OnStartup called ONCE for each async backend in use (used by this system's PIs)
Via the asynchronous.py, after visiting all params and collecting them,
for each asn.1 type that is actually used (at least once) as a param:
    Call Encoder and Decoder
Call OnShutdown ONCE for each async backend in use (used by this system's PIs)

3. Special backends
===================

GUI, Python, (VHDL?), etc...

These have custom requirements, so each one is handled by specific AADL2GLUEC
code. As it is now, the pattern follows that of the synchronous backends,
but with an extra call to OnFinal at the end.
'''

import os
import sys
import copy
import distutils.spawn as spawn

from types import ModuleType
from typing import Dict, List, Tuple, Any  # NOQA pylint: disable=unused-import

# from importlib import import_module
from .B_mappers import ada_B_mapper
from .B_mappers import c_B_mapper
from .B_mappers import gui_B_mapper
from .B_mappers import og_B_mapper
from .B_mappers import sdl_B_mapper
from .B_mappers import pyside_B_mapper
from .B_mappers import python_B_mapper
from .B_mappers import qgenada_B_mapper
from .B_mappers import qgenc_B_mapper
from .B_mappers import rtds_B_mapper
from .B_mappers import scade6_B_mapper
from .B_mappers import simulink_B_mapper
from .B_mappers import vhdl_B_mapper

from . import commonPy

from .commonPy.utility import panic, inform
from .commonPy import verify
from .commonPy.cleanupNodes import DiscoverBadTypes, SetOfBadTypenames
from .commonPy.asnParser import Filename, Typename, AST_Lookup, AST_TypesOfFile, AST_Leaftypes  # NOQA pylint: disable=unused-import
from .commonPy.asnAST import AsnNode  # NOQA pylint: disable=unused-import
from .commonPy.aadlAST import ApLevelContainer  # NOQA pylint: disable=unused-import

from . import B_mappers  # NOQA pylint: disable=unused-import

# To unpickle the Py2/ANTLR2-generated pickle file...
#    http://stackoverflow.com/questions/2121874/python-pickling-after-changing-a-modules-directory
from . import commonPy2
sys.modules['commonPy2'] = commonPy2


def ParseAADLfilesAndResolveSignals() -> None:
    '''Invokes the ANTLR generated AADL parser, and resolves
all references to AAADL Data types into the param._signal member
of each SUBPROGRAM param.'''
    import tempfile
    f = tempfile.NamedTemporaryFile(delete=False)
    astFile = f.name
    f.close()
    os.unlink(astFile)
    parserUtility = os.path.join(os.path.abspath(os.path.dirname(__file__)), "parse_aadl.py")
    cmd = "python2 " + parserUtility + " -o " + astFile + ' ' + ' '.join(sys.argv[1:])
    if os.system(cmd) != 0:
        if os.path.exists(astFile):
            os.unlink(astFile)
        panic("AADL parsing failed. Aborting...")

    def FixMetaClasses(sp: ApLevelContainer) -> None:
        def patchMe(o: Any) -> None:
            try:
                python2className = str(o.__class__).split("'")[1]
                if 'commonPy2' in python2className:
                    klass = commonPy
                    for step in python2className.split('.')[1:]:
                        klass = getattr(klass, step)
                    o.__class__ = klass
            except Exception as _:
                pass

        patchMe(sp)
        for param in sp._params:
            patchMe(param)
            patchMe(param._signal)
            patchMe(param._sourceElement)
        # for c in sp._calls:
        #     patchMe(c)
        for cn in sp._connections:
            patchMe(cn)
    try:
        import pickle
        astInfo = pickle.load(open(astFile, 'rb'), fix_imports=False)
        for k in ['g_processImplementations', 'g_apLevelContainers',
                  'g_signals', 'g_systems', 'g_subProgramImplementations',
                  'g_threadImplementations']:
            setattr(commonPy.aadlAST, k, astInfo[k])
        for k in ['g_processImplementations',
                  'g_subProgramImplementations', 'g_threadImplementations']:
            for si in astInfo[k]:
                # sp, sp_impl, modelingLanguage, maybeFVname = si[0], si[1], si[2], si[3]
                sp = si[0]
                sp = commonPy.aadlAST.g_apLevelContainers[sp]
                FixMetaClasses(sp)
    except Exception as e:
        if os.path.exists(astFile):
            os.unlink(astFile)
        panic(str(e))


def SpecialCodes(unused_SystemsAndImplementations: List[Tuple[str, str, str, str]],
                 unused_uniqueDataFiles: Dict[Filename, Dict[str, List[ApLevelContainer]]],  # pylint: disable=invalid-sequence-index
                 asnFiles: Dict[Filename, Tuple[AST_Lookup, List[AsnNode], AST_Leaftypes]],  # pylint: disable=invalid-sequence-index
                 unused_useOSS: bool) -> None:
    '''This function handles the code generations needs that reside outside
the scope of individual parameters (e.g. it needs access to all ASN.1
types). This used to cover Dumpable C/Ada Types and OG headers.'''
    outputDir = commonPy.configMT.outputDir
    asn1SccPath = spawn.find_executable('asn1.exe')
    if len(asnFiles) != 0:
        if not asn1SccPath:
            panic("ASN1SCC seems not installed on your system (asn1.exe not found in PATH).\n")  # pragma: no cover
        os.system('mono "{}" -wordSize 8 -typePrefix asn1Scc -Ada -equal -uPER -o "{}" "{}"'
                  .format(asn1SccPath, outputDir, '" "'.join(asnFiles)))


def main() -> None:
    if "-v" in sys.argv:
        import pkg_resources  # pragma: no cover
        version = pkg_resources.require("dmt")[0].version  # pragma: no cover
        print("aadl2glueC v" + str(version))  # pragma: no cover
        sys.exit(1)  # pragma: no cover

    if sys.argv.count("-o") != 0:
        idx = sys.argv.index("-o")
        try:
            commonPy.configMT.outputDir = os.path.normpath(sys.argv[idx + 1]) + os.sep
        except:  # pragma: no cover
            panic('Usage: %s [-v] [-verbose] [-useOSS] [-o dirname] input1.aadl [input2.aadl] ...\n' % sys.argv[0])  # pragma: no cover
        del sys.argv[idx]
        del sys.argv[idx]
        if not os.path.isdir(commonPy.configMT.outputDir):
            panic("'%s' is not a directory!\n" % commonPy.configMT.outputDir)  # pragma: no cover
    if "-onlySP" in sys.argv:  # pragma: no cover
        commonPy.configMT.g_bOnlySubprograms = True  # pragma: no cover
        sys.argv.remove("-onlySP")  # pragma: no cover
    if "-verbose" in sys.argv:
        commonPy.configMT.verbose = True
        sys.argv.remove("-verbose")
    useOSS = "-useOSS" in sys.argv
    if useOSS:
        sys.argv.remove("-useOSS")

    # No other options must remain in the cmd line...
    if len(sys.argv) < 2:
        panic('Usage: %s [-v] [-verbose] [-useOSS] [-o dirname] input1.aadl [input2.aadl] ...\n' % sys.argv[0])  # pragma: no cover
    commonPy.configMT.showCode = True
    for f in sys.argv[1:]:
        if not os.path.isfile(f):
            panic("'%s' is not a file!\n" % f)  # pragma: no cover

    ParseAADLfilesAndResolveSignals()

    uniqueDataFiles = {}  # type: Dict[Filename, Dict[str, List[ApLevelContainer]]]
    for sp in list(commonPy.aadlAST.g_apLevelContainers.values()):
        for param in sp._params:
            uniqueDataFiles.setdefault(param._signal._asnFilename, {})
            uniqueDataFiles[param._signal._asnFilename].setdefault(sp._language, [])
            uniqueDataFiles[param._signal._asnFilename][sp._language].append(sp)

    uniqueASNfiles = {}  # type: Dict[Filename, Tuple[AST_Lookup, List[AsnNode], AST_Leaftypes]]
    if len(list(uniqueDataFiles.keys())) != 0:
        commonPy.asnParser.ParseAsnFileList(list(uniqueDataFiles.keys()))

    for asnFile in uniqueDataFiles:
        tmpNames = {}  # type: AST_Lookup
        for name in commonPy.asnParser.g_typesOfFile[asnFile]:
            tmpNames[name] = commonPy.asnParser.g_names[name]

        uniqueASNfiles[asnFile] = (
            copy.copy(tmpNames),                            # map Typename to type definition class from asnAST
            copy.copy(commonPy.asnParser.g_astOfFile[asnFile]),    # list of nameless type definitions
            copy.copy(commonPy.asnParser.g_leafTypeDict))   # map from Typename to leafType

        inform("Checking that all base nodes have mandatory ranges set in %s..." % asnFile)
        for node in list(tmpNames.values()):
            verify.VerifyRanges(node, commonPy.asnParser.g_names)

    SystemsAndImplementations = commonPy.aadlAST.g_subProgramImplementations[:]
    SystemsAndImplementations.extend(commonPy.aadlAST.g_threadImplementations[:])
    SystemsAndImplementations.extend(commonPy.aadlAST.g_processImplementations[:])

    # Update ASN.1 nodes to carry size info (only for Signal params)
    for si in SystemsAndImplementations:
        spName, sp_impl, modelingLanguage = si[0], si[1], si[2]
        sp = commonPy.aadlAST.g_apLevelContainers[spName]
        for param in sp._params:
            asnFile = param._signal._asnFilename
            names = uniqueASNfiles[asnFile][0]
            for nodeTypename in names:
                if nodeTypename != param._signal._asnNodename:
                    continue
                node = names[nodeTypename]
                if node._leafType == "AsciiString":
                    panic("You cannot use IA5String as a parameter - use OCTET STRING instead\n(%s)" % node.Location())  # pragma: no cover
                # (typo?) node._asnSize = param._signal._asnSize

    # If some AST nodes must be skipped (for any reason), go learn about them
    badTypes = DiscoverBadTypes()

    if {"ada", "qgenada"} & {y[2].lower() for y in SystemsAndImplementations}:
        SpecialCodes(SystemsAndImplementations, uniqueDataFiles, uniqueASNfiles, useOSS)

    asynchronousBackends = set([])  # type: Set[ModuleType]

    # Moving to static typing - no more dynamic imports,
    # so this information must be statically available
    async_languages = ['Ada', 'C', 'OG', 'QGenAda', 'rtds', 'SDL']

    for si in SystemsAndImplementations:
        spName, sp_impl, modelingLanguage, maybeFVname = si[0], si[1], si[2], si[3]
        if modelingLanguage is None:
            continue  # pragma: no cover
        sp = commonPy.aadlAST.g_apLevelContainers[spName]
        inform("Creating glue for parameters of %s.%s...", sp._id, sp_impl)

        # Avoid generating empty glue - no parameters for this APLC
        if len(sp._params) == 0:
            continue

        # All SCADE versions are handled by lustre_B_mapper
        # if modelingLanguage[:6] == "Lustre" or modelingLanguage[:5] == "SCADE":
        #    modelingLanguage = "Lustre"  # pragma: no cover

        # The code for these mappers needs C ASN.1 codecs
        if modelingLanguage.lower() in ["gui_ri", "gui_pi", "vhdl", "rhapsody"]:
            modelingLanguage = "C"

        if modelingLanguage in async_languages:
            m = ProcessAsync(modelingLanguage, asnFile, sp, maybeFVname, useOSS, badTypes)
            asynchronousBackends.add(m)
        else:
            ProcessSync(modelingLanguage, asnFile, sp, sp_impl, maybeFVname, useOSS, badTypes)

    # SystemsAndImplementation loop completed - time to call OnShutdown ONCE for each async backend that we loaded
    for asyncBackend in asynchronousBackends:
        asyncBackend.OnShutdown(modelingLanguage, asnFile, maybeFVname)

    ProcessCustomBackends(asnFile, useOSS, SystemsAndImplementations)


def getBackend(modelingLanguage: str) -> ModuleType:  # pylint: disable=too-many-return-statements
    if modelingLanguage == 'C':
        return c_B_mapper
    elif modelingLanguage == 'Ada':
        return ada_B_mapper
    elif modelingLanguage == 'SDL':
        return sdl_B_mapper
    elif modelingLanguage == 'OG':
        return og_B_mapper
    elif modelingLanguage == 'QGenAda':
        return qgenada_B_mapper
    elif modelingLanguage == 'rtds':
        return rtds_B_mapper
    elif modelingLanguage == 'gui':
        return gui_B_mapper
    elif modelingLanguage == 'python':
        return python_B_mapper
    elif modelingLanguage == 'QgenC':
        return qgenc_B_mapper
    elif modelingLanguage == 'Scade6':
        return scade6_B_mapper
    elif modelingLanguage == 'Simulink':
        return simulink_B_mapper
    elif modelingLanguage == 'vhdl':
        return vhdl_B_mapper
    else:
        panic("Modeling language '%s' not supported" % modelingLanguage)


def ProcessSync(
        modelingLanguage: str,
        asnFile: str,
        sp: ApLevelContainer,
        sp_impl: str,
        maybeFVname: str,
        useOSS: bool,
        badTypes: SetOfBadTypenames):
    backend = getBackend(modelingLanguage)

    # Asynchronous backends are only generating standalone encoders and decoders
    # (they are not doing this per sp.param).
    #
    # They must however do this when they have collected ALL the types they are
    # supposed to handle, so this can only be done when the loop over
    # SystemsAndImplementations has completed. We therefore accumulate them in a
    # container, and call their 'OnShutdown' method (which generates the encoders
    # and decoders) at the end (outside the loop). This of course means that we
    # can only call OnStartup once (when the backend is first loaded)

    # In synchronous tools, always call OnStartup and OnShutdown for each SystemsAndImplementation
    backend.OnStartup(modelingLanguage, asnFile, sp, sp_impl, commonPy.configMT.outputDir, maybeFVname, useOSS)

    for param in sp._params:
        inform("Creating glue for param %s...", param._id)
        asnFile = param._signal._asnFilename
        names = commonPy.asnParser.g_names
        leafTypeDict = commonPy.asnParser.g_leafTypeDict

        inform("This param uses definitions from %s", asnFile)
        nodeTypename = param._signal._asnNodename

        # Check if this type must be skipped
        if nodeTypename in badTypes:
            continue

        node = names[nodeTypename]
        inform("ASN.1 node is %s", nodeTypename)

        # First, make sure we know what leaf type this node is
        if node._isArtificial:
            continue  # artificially created (inner) type

        leafType = leafTypeDict[nodeTypename]
        if leafType in ['BOOLEAN', 'INTEGER', 'REAL', 'OCTET STRING']:
            processor = backend.OnBasic
        elif leafType == 'SEQUENCE':
            processor = backend.OnSequence
        elif leafType == 'SET':
            processor = backend.OnSet
        elif leafType == 'CHOICE':
            processor = backend.OnChoice
        elif leafType == 'SEQUENCEOF':
            processor = backend.OnSequenceOf
        elif leafType == 'SETOF':
            processor = backend.OnSetOf
        elif leafType == 'ENUMERATED':
            processor = backend.OnEnumerated
        else:  # pragma: no cover
            panic("Unexpected type of element: %s" % leafType)  # pragma: no cover
        processor(nodeTypename, node, sp, sp_impl, param, leafTypeDict, names)

    # For synchronous backend, call OnShutdown once per each sp_impl
    backend.OnShutdown(modelingLanguage, asnFile, sp, sp_impl, maybeFVname)


def ProcessAsync(  # pylint: disable=dangerous-default-value
        modelingLanguage: str,
        asnFile: str,
        sp: ApLevelContainer,
        maybeFVname: str,
        useOSS: bool,
        badTypes: SetOfBadTypenames,
        loaded_languages_cache: List[str]=[]) -> ModuleType:  # pylint: disable=invalid-sequence-index

    backend = getBackend(modelingLanguage)

    # Asynchronous backends are only generating standalone encoders and decoders
    # (they are not doing this per sp.param).
    #
    # They must however do this when they have collected ALL the types they are
    # supposed to handle, so this can only be done when the loop over
    # SystemsAndImplementations has completed. We therefore accumulate them in a
    # container, and call their 'OnShutdown' method (which generates the encoders
    # and decoders) at the end (outside the loop). This of course means that we
    # can only call OnStartup once (when the backend is first loaded)
    if modelingLanguage not in loaded_languages_cache:
        loaded_languages_cache.append(modelingLanguage)
        # Only call OnStartup ONCE for asynchronous backends
        # Also notice, no SP or SPIMPL are passed. We are asynchronous, so
        # we only generate "generic" encoders and decoders, not SP-specific ones.
        backend.OnStartup(modelingLanguage, asnFile, commonPy.configMT.outputDir, maybeFVname, useOSS)

    for param in sp._params:
        inform("Creating glue for param %s...", param._id)
        asnFile = param._signal._asnFilename
        names = commonPy.asnParser.g_names
        leafTypeDict = commonPy.asnParser.g_leafTypeDict

        inform("This param uses definitions from %s", asnFile)
        for nodeTypename in names:
            # Check if this type must be skipped
            if nodeTypename in badTypes:
                continue

            # Async backends need to collect all types and create Encode/Decode functions for them.
            # So we allow async backends to pass thru this "if" - the collection of types
            # is done in the typesToWorkOn dictionary *inside* the base class (asynchronousTool.py)
            if (not backend.isAsynchronous) and nodeTypename != param._signal._asnNodename:
                # For sync tools, only allow the typename we are using in this param to pass
                continue
            node = names[nodeTypename]
            inform("ASN.1 node is %s", nodeTypename)

            # First, make sure we know what leaf type this node is
            if node._isArtificial:
                continue  # artificially created (inner) type

            leafType = leafTypeDict[nodeTypename]
            if leafType in ['BOOLEAN', 'INTEGER', 'REAL', 'OCTET STRING']:
                processor = backend.OnBasic
            elif leafType == 'SEQUENCE':
                processor = backend.OnSequence
            elif leafType == 'SET':
                processor = backend.OnSet
            elif leafType == 'CHOICE':
                processor = backend.OnChoice
            elif leafType == 'SEQUENCEOF':
                processor = backend.OnSequenceOf
            elif leafType == 'SETOF':
                processor = backend.OnSetOf
            elif leafType == 'ENUMERATED':
                processor = backend.OnEnumerated
            else:  # pragma: no cover
                panic("Unexpected type of element: %s" % leafType)  # pragma: no cover
            processor(nodeTypename, node, leafTypeDict, names)
    return backend


def ProcessCustomBackends(
        # Taking list of tuples made of (spName, sp_impl, language, maybeFVname)
        asnFile: str,
        useOSS: bool,
        SystemsAndImplementations: List[Tuple[str, str, str, str]]) -> None:

    # The code generators for GUIs, Python mappers and VHDL mappers are different: they need access to
    # both ASN.1 types and SP params.
    # Custom code follows...

    # Do we need to handle any special subprograms?
    workedOnGUIs = False
    workedOnVHDL = False

    def getCustomBackends(lang: str) -> List[ModuleType]:  # pylint: disable=invalid-sequence-index
        if lang.lower() in ["gui_pi", "gui_ri"]:
            return [python_B_mapper, pyside_B_mapper]  # pragma: no cover
        elif lang.lower() == "vhdl":  # pragma: no cover
            return [vhdl_B_mapper]  # pragma: no cover

    for si in [x for x in SystemsAndImplementations if x[2] is not None and x[2].lower() in ["gui_ri", "gui_pi", "vhdl"]]:
        # We do, start the work
        spName, sp_impl, lang, maybeFVname = si[0], si[1], si[2], si[3]
        sp = commonPy.aadlAST.g_apLevelContainers[spName]
        if len(sp._params) == 0:
            if lang.lower() == "gui_ri":  # pragma: no cover
                if "gui_polling" not in sp._id:  # pragma: no cover
                    panic("Due to wxWidgets limitations, your TCs must have at least one parameter (fix %s)" % sp._id)  # pragma: no cover
            continue  # pragma: no cover
        if lang.lower() in ["gui_pi", "gui_ri"]:
            workedOnGUIs = True
        if lang.lower() == "vhdl":
            workedOnVHDL = True  # pragma: no cover
        inform("Creating %s for %s.%s", lang.upper(), sp._id, sp_impl)
        for backend in getCustomBackends(lang):
            backend.OnStartup(lang, asnFile, sp, sp_impl, commonPy.configMT.outputDir, maybeFVname, useOSS)
        for param in sp._params:
            inform("Processing param %s...", param._id)
            asnFile = param._signal._asnFilename
            names = commonPy.asnParser.g_names
            leafTypeDict = commonPy.asnParser.g_leafTypeDict
            nodeTypename = param._signal._asnNodename
            node = names[nodeTypename]
            inform("ASN.1 node is %s", nodeTypename)
            # if node._isArtificial:
            #     continue # artificially created (inner) type pragma: no cover
            leafType = leafTypeDict[nodeTypename]
            if leafType in ['BOOLEAN', 'INTEGER', 'REAL', 'OCTET STRING']:
                for backend in getCustomBackends(lang):
                    backend.OnBasic(nodeTypename, node, sp, sp_impl, param, leafTypeDict, names)
            elif leafType in ['SEQUENCE', 'SET', 'CHOICE', 'SEQUENCEOF', 'SETOF', 'ENUMERATED']:
                for backend in getCustomBackends(lang):
                    if leafType == 'SEQUENCE':
                        processor = backend.OnSequence
                    elif leafType == 'SET':
                        processor = backend.OnSet
                    elif leafType == 'CHOICE':
                        processor = backend.OnChoice
                    elif leafType == 'SEQUENCEOF':
                        processor = backend.OnSequenceOf
                    elif leafType == 'SETOF':
                        processor = backend.OnSetOf
                    elif leafType == 'ENUMERATED':
                        processor = backend.OnEnumerated
                    processor(nodeTypename, node, sp, sp_impl, param, leafTypeDict, names)
            else:  # pragma: no cover
                panic("Unexpected type of element: %s" % leafTypeDict[nodeTypename])  # pragma: no cover
        for backend in getCustomBackends(lang):
            backend.OnShutdown(lang, asnFile, sp, sp_impl, maybeFVname)

    # if we processed any GUI subprogram, add footers and close files
    if workedOnGUIs:
        for backend in getCustomBackends('gui_ri'):
            backend.OnFinal()
    # if we processed any VHDL subprogram, add footers and close files
    if workedOnVHDL:
        for backend in getCustomBackends('vhdl'):  # pragma: no cover
            backend.OnFinal()  # pragma: no cover


if __name__ == "__main__":
    if "-pdb" in sys.argv:
        sys.argv.remove("-pdb")  # pragma: no cover
        import pdb  # pragma: no cover pylint: disable=wrong-import-position,wrong-import-order
        pdb.run('main()')  # pragma: no cover
    else:
        main()
