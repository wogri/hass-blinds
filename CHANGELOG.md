# Changelog

## Unreleased

- Added `tilt_mode: immediate` to send position and tilt commands without the default tilt delay for covers that support both on the same Home Assistant entity.
- Fixed kill switch reactivation after release when the blind still needs to move to the desired automation target.
- Updated the global kill switch entity documentation to `input_boolean.raffstore_kill_switch`.
- Updated extreme heat timestamp handling to use `datetime.datetime.now()`.
- Added a unit test for immediate tilt command execution.
