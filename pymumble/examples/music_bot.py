#!/usr/bin/python3

import pymumble_py3
import subprocess as sp
import audioop, time
import argparse

parser = argparse.ArgumentParser(description='get parameters.')

parser.add_argument('--server', '-s', required=True)
parser.add_argument('--port', '-P', type=int, default=64738)
parser.add_argument('--name', '-n', required=True)
parser.add_argument('--passwd', '-p', default="")
parser.add_argument('file')
args = parser.parse_args()

file = args.file
server = args.server
nick = args.name
passwd = args.passwd
port = args.port

mumble = pymumble_py3.Mumble(server, nick, password=passwd, port=port)
mumble.start()
mumble.is_ready()   #wait for Mumble to get ready to avoid errors after startup

while True:
    print("start Processing")
    command = ["ffmpeg", "-i", file, "-acodec", "pcm_s16le", "-f", "s16le", "-ab", "192k", "-ac", "1", "-ar", "48000",  "-"]
    sound = sp.Popen(command, stdout=sp.PIPE, stderr=sp.DEVNULL, bufsize=1024)
    print("playing")
    while True:
        raw_music = sound.stdout.read(1024)
        if not raw_music:
            break
        #mumble.sound_output.add_sound(audioop.mul(raw_music, 2, vol))   #adjusting volume
        mumble.sound_output.add_sound(raw_music)
    print("finished")
    while mumble.sound_output.get_buffer_size() > 0.5:  #
        time.sleep(0.01)
    print("sleep")
    time.sleep(2)
