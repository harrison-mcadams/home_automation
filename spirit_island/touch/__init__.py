"""Camera input for the game: finger counts, a held fingertip, swipes, a double tap, and
cards laid on the input mat. Nothing here knows the game; it only reports what the hand did.

    gestures.py  turns hand landmarks over time into events (pure logic, no camera)
    hands.py     finds hand landmarks in a frame with MediaPipe
    mat.py       finds the dark input mat and any card lying on it
    test_page.py the stage 2 touch test: live view, prompts and a score
"""
