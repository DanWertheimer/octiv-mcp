import os

# Must be set before any test module imports server.py,
# which instantiates OctivClient() at module level.
os.environ.setdefault("OCTIV_USERNAME", "test@example.com")
os.environ.setdefault("OCTIV_PASSWORD", "testpass")
