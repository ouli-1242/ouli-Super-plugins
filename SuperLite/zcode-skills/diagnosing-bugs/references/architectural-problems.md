# Architectural Problems (when 3+ fixes fail)

This is not a failed hypothesis — this is a wrong architecture. Patterns indicating an architectural problem:

- Each fix reveals new shared state / coupling in a different place
- Fixes keep requiring "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

Discuss whether to refactor the architecture instead of continuing to fix symptoms. Do not attempt fix #4 without an architectural discussion with the user.
