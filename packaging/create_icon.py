from pathlib import Path
from PIL import Image, ImageDraw
image=Image.new('RGBA',(256,256),(0,0,0,0))
draw=ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248),radius=52,fill='#265c3b')
draw.rounded_rectangle((43,57,213,188),radius=25,outline='#eef6e6',width=12)
draw.line((78,103,177,103),fill='#eef6e6',width=12)
draw.line((78,144,147,144),fill='#b9d7ed',width=12)
image.save(Path(__file__).with_name('suiyi.ico'),sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
