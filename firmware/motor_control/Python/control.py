import serial
import pygame
import time

pygame.init()
pygame.joystick.init()

# Xbox Connection
joystick = None

if pygame.joystick.get_count() > 0:
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print("Connected:", joystick.get_name())

# Serial Communication
ser = serial.Serial("COM9", 115200, write_timeout=0.2)
time.sleep(3)

screen = pygame.display.set_mode((500, 250))
clock = pygame.time.Clock()
font = pygame.font.SysFont("Arial", 24)

mode = "PC"
running = True


# Vision Data
def get_vision_data():

    # TODO: Receive int16 deltaX, deltaY from Vision
    deltaX = 0
    deltaY = 0
    flag = 0

    return int(deltaX), int(deltaY), flag


try:
    while running:
        shot_requested = False

        # Event Processing
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:

                if event.key == pygame.K_F1:
                    mode = "PC"

                elif event.key == pygame.K_F2:
                    mode = "MANUAL"

                elif event.key == pygame.K_F3:
                    mode = "AUTO"

                elif event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_SPACE:
                    if mode == "PC" and pygame.key.get_focused():
                        shot_requested = True

            elif event.type == pygame.JOYDEVICEADDED:
                if joystick is None:
                    joystick = pygame.joystick.Joystick(
                        event.device_index
                    )
                    joystick.init()

            elif event.type == pygame.JOYDEVICEREMOVED:
                joystick = None

        if not running:
            break

        # Default: IDLE
        data = "I"

        if pygame.key.get_focused():

            # PC Mode
            if mode == "PC":

                keys = pygame.key.get_pressed()
                cmd = "x"

                if keys[pygame.K_a]:
                    cmd = "a"
                elif keys[pygame.K_d]:
                    cmd = "d"
                elif keys[pygame.K_w]:
                    cmd = "w"
                elif keys[pygame.K_s]:
                    cmd = "s"

                data = f"P,{cmd}"

            # Manual Mode
            elif mode == "MANUAL":

                if joystick is not None:
                    x = round(joystick.get_axis(0) * 1200)
                    y = round(-joystick.get_axis(1) * 1200)

                    data = f"M,{x},{y}"

            # Auto Mode
            elif mode == "AUTO":

                deltaX, deltaY, flag = get_vision_data()

                data = f"A,{deltaX},{deltaY},{flag}"

        # Serial Transmission
        ser.write(f"{data}\n".encode())

        if shot_requested and mode == "PC":
            ser.write(b"X\n")

        # Display
        screen.fill((25, 25, 25))

        lines = [
            f"Mode: {mode}",
            f"Command: {data}",
            "F1: PC   F2: MANUAL   F3: AUTO",
            "ESC: Exit",
            f"Xbox: {'Connected' if joystick else 'Disconnected'}"
        ]

        for i, line in enumerate(lines):
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (20, 20 + i * 42))

        pygame.display.set_caption("Pan & Tilt Control")
        pygame.display.flip()

        # 20 Hz
        clock.tick(20)

finally:
    try:
        ser.write(b"I\n")
        ser.flush()
    finally:
        ser.close()
        pygame.quit()
