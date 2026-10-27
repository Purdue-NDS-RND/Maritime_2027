# Ground station

Future independently runnable, containerized web application for reviewing the
drone's object map, generating a predefined GPS route, preparing task
instructions, uploading the mission to the boat, and monitoring both vehicles.

Object positions describe where objects are; route waypoints describe where
the boat should travel. Keep these distinct. The UI runs in a browser, with React
and FastAPI as the preferred, provisional frontend/backend stack. Hosting,
vehicle networking, route generation, and mission protocols remain undecided.
This is a scaffold only.
