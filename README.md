[![Build and Test Status of Data Modelling Tools on Circle CI](https://circleci.com/gh/ttsiodras/DataModellingTools.svg?&style=shield&circle-token=9df10d36b6b4ccd923415a5890155b7bf54b95c5)](https://circleci.com/gh/ttsiodras/DataModellingTools/tree/master)

TASTE Data Modelling Tools
==========================

These are all the tools used by the [TASTE toolchain](https://taste.tuxfamily.org/)
to automate handling of the Data Modelling challenges. They include more than two
dozen codegenerators that create the 'glue' ; that is, the code allowing code
generated by modelling tools (Simulink, SCADE, OpenGeode, etc) to "speak" to
one another via ASN.1 marshalling. For the encoders and decoders of the messages
themselves, we use [ASN1SCC](https://github.com/ttsiodras/asn1scc) - an ASN.1
compiler geared for safety-critical environments.

For more details, visit the [TASTE site](https://taste.tuxfamily.org/).

Installation
------------

    $ sudo apt-get install libxslt-dev libxml2-dev python3-pip
    $ pip3 install --user -r requirements.txt
    $ make flake8  # optional, check for pep8 compliance
    $ make pylint  # optional, static analysis with pylint
    $ make mypy  # optional, type analysis with mypy
    $ pip3 install --user --upgrade .

For developers
--------------

    $ pip3 install --user --upgrade --editable .


Contents
--------

- **commonPy** (*library*)

    Contains the basic API for parsing ASN.1 (via invocation of 
    [ASN1SCC](https://github.com/ttsiodras/asn1scc) and simplification
    of the generated XML AST representation to the Python classes
    inside `asnAST.py`.

- **asn2aadlPlus** (*utility*)

    Converts the type declarations inside ASN.1 grammars to AADL
    declarations (used by the Ellidiss tools to design the final systems)

- **asn2dataModel** (*utility*)

    Reads the ASN.1 specification of the exchanged messages, and generates
    the semantically equivalent Modeling tool/Modeling language declarations
    (e.g.  SCADE/Lustre, Matlab/Simulink statements, etc). 

    The actual mapping logic exists in plugins, called *A mappers*
    (`simulink_A_mapper.py` handles Simulink/RTW, `scade6_A_mapper.py`
    handles SCADE5, `ada_A_mapper.py` generates Ada types,
    `sqlalchemy_A_mapper.py`, generates SQL definitions via SQLAlchemy, etc)

- **aadl2glueC** (*utility*)

    Reads the AADL specification of the system, and then generates the runtime
    bridge-code that will map the message data structures from those generated
    by [ASN1SCC](https://github.com/ttsiodras/asn1scc) to/from those generated
    by the modeling tool used to functionally model the subsystem (e.g. SCADE,
    ObjectGeode, Matlab/Simulink, C, Ada, etc).

Contact
-------

For bug reports, please use the Issue Tracker; for any other communication,
contact me at:

    Thanassis Tsiodras
    Real-time Embedded Software Engineer 
    System, Software and Technology Department
    European Space Agency

    ESTEC
    Keplerlaan 1, PO Box 299
    NL-2200 AG Noordwijk, The Netherlands
    Athanasios.Tsiodras@esa.int | www.esa.int
    T +31 71 565 5332
