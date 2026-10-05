"""Suite-wide determinism for the advertised surface.

`FASTGRAPH_PROFILE` and `FASTGRAPH_MEMORY` decide which tools a process registers,
and both are read when a server is built, not at import -- so without this, a
developer running the tests with either variable set in their shell would watch
surface pins fail for a reason unrelated to the code under test. The values pinned
here are the shipped defaults: full profile, memory layer on. Tests that exercise
another combination set the variable themselves (monkeypatch or os.environ) and
still get their value.
"""
import os

os.environ["FASTGRAPH_PROFILE"] = "full"
os.environ["FASTGRAPH_MEMORY"] = "1"
