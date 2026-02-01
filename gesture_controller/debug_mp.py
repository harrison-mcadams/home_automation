import sys
print(f"Python executable: {sys.executable}")
try:
    import mediapipe
    print(f"MediaPipe version: {mediapipe.__version__}")
    print(f"MediaPipe file: {mediapipe.__file__}")
    print("dir(mediapipe):")
    print(dir(mediapipe))
    
    if hasattr(mediapipe, 'solutions'):
        print("mediapipe.solutions found")
    else:
        print("mediapipe.solutions NOT found")
        
    try:
        import mediapipe.python.solutions
        print("Successfully imported mediapipe.python.solutions")
    except ImportError as e:
        print(f"Failed to import mediapipe.python.solutions: {e}")
        
except ImportError as e:
    print(f"Failed to import mediapipe: {e}")
