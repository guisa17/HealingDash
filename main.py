import os
import sys
import math
import random
import asyncio

import pygame

from scripts.utils import load_image, load_images, Animation
from scripts.entities import PhysicsEntity, Player, Enemy, Fruit
from scripts.tilemap import Tilemap
from scripts.clouds import Clouds
from scripts.particle import Particle
from scripts.spark import Spark


class Game:
    def __init__(self):
        # Inicializamos los módulos de Pygame
        pygame.init()

        # Inicializamos títulos de la ventana
        pygame.display.set_caption('demo')

        # Creamos ventana del juego 640x480
        self.screen = pygame.display.set_mode((640, 480))

        # Superficie para outline (contorno) | SRCALPHA añade transparency
        self.display = pygame.Surface((320, 240), pygame.SRCALPHA) 

        # Superficie para renderizar
        self.display_2 = pygame.Surface((320, 240))

        # Tasa de fps
        self.clock = pygame.time.Clock()
        
        # Movimiento derecha / izquierda
        self.movement = [False, False]
        
        # Cargamos imágenes y animaciones
        self.assets = {
            'decor': load_images('tiles/decor'),
            'grass': load_images('tiles/grass'),
            'large_decor': load_images('tiles/large_decor'),
            'stone': load_images('tiles/stone'),
            'player': load_image('entities/player.png'),
            'background': load_image('background.png'),
            'clouds': load_images('clouds'),
            'enemy/idle': Animation(load_images('entities/enemy/idle'), img_dur=6),
            'enemy/run': Animation(load_images('entities/enemy/run'), img_dur=4),
            'player/idle': Animation(load_images('entities/player/idle'), img_dur=6),
            'player/run': Animation(load_images('entities/player/run'), img_dur=4),
            'player/jump': Animation(load_images('entities/player/jump')),
            'player/slide': Animation(load_images('entities/player/slide')),
            'player/wall_slide': Animation(load_images('entities/player/wall_slide')),
            'particle/leaf': Animation(load_images('particles/leaf'), img_dur=20, loop=False),
            'particle/particle': Animation(load_images('particles/particle'), img_dur=6, loop=False),
            'healed': load_image('entities/healed.png'),
            'fruit/apple': load_image('tiles/fruits/apple.png'),
        }
        
        # Cargamos y configuramos efectos de sonido 
        self.sfx = {
            'jump': pygame.mixer.Sound('data/sfx/jump.wav'),
            'dash': pygame.mixer.Sound('data/sfx/dash.wav'),
            'hit': pygame.mixer.Sound('data/sfx/hit.wav'),
            'ambience': pygame.mixer.Sound('data/sfx/ambience.wav'),
            'cough': pygame.mixer.Sound('data/sfx/cough.wav'),
            'munch': pygame.mixer.Sound('data/sfx/munch.wav'), 
        }
        # Volumen (0 - 1)
        self.sfx['ambience'].set_volume(0.2)
        self.sfx['hit'].set_volume(0.7)
        self.sfx['dash'].set_volume(0.3)
        self.sfx['jump'].set_volume(0.6)
        self.sfx['cough'].set_volume(0.3)
        
        # Creamos en el orden en el que se rendizarán (nubes -> jugador -> mapa)
        self.clouds = Clouds(self.assets['clouds'], count=16)
        self.player = Player(self, (50, 50), (8, 15))
        self.tilemap = Tilemap(self, tile_size=16)
        
        # Nivel inicial del juego
        self.level = 0
        self.load_level(self.level)

        self.healed_count = 0

        # Vibración de la pantalla 
        self.screenshake = 0

    def load_level(self, map_id):
        # Cargamos el mapa actual
        self.tilemap.load('data/maps/' + str(map_id) + '.json')
        
        # Spawner de hojas (partículas)
        self.leaf_spawners = []
        for tree in self.tilemap.extract([('large_decor', 2)], keep=True):
            # Definimos área de spawn
            self.leaf_spawners.append(pygame.Rect(4 + tree['pos'][0], 4 + tree['pos'][1], 23, 13))

        self.enemies = []
        for spawner in self.tilemap.extract([('spawners', 0), ('spawners', 1)]):
            # Spawn del jugador
            if spawner['variant'] == 0:
                self.player.pos = spawner['pos']
                self.player.air_time = 0
            else:
                # Spawn de los enemigos
                self.enemies.append(Enemy(self, spawner['pos'], (8, 15)))

        self.fruits = []
        for fruit_spawner in self.tilemap.extract([('decor', 0)], keep=True):
            self.fruits.append(Fruit(self, fruit_spawner['pos'], fruit_type='apple'))

        self.particles = []
        self.sparks = []
        
        # Desplazamiento de nuestra cámara
        self.scroll = [0, 0]

        self.dead = 0
        self.transition = -30

        # Reinicia la vida del jugador
        self.player.health = self.player.max_health

        # Reinicia defeated status para enemigos
        for enemy in self.enemies:
            enemy.defeated = False


    def draw_health_bar(self, surf, x, y, pct):
        if pct < 0:
            pct = 0
        BAR_LENGTH = 100
        BAR_HEIGHT = 10
        fill = (pct / 100) * BAR_LENGTH
        outline_rect = pygame.Rect(x, y, BAR_LENGTH, BAR_HEIGHT)
        fill_rect = pygame.Rect(x, y, fill, BAR_HEIGHT)
        col = (255, 0, 0)
        pygame.draw.rect(surf, col, fill_rect)
        pygame.draw.rect(surf, (255, 255, 255), outline_rect, 2)
    

    def draw_healed_counter(self, surf):
        img = self.assets['healed']
        surf.blit(img, (surf.get_width() - img.get_width() - 10, 10))  # Dibuja la imagen en la esquina superior derecha
        font = pygame.font.SysFont(None, 24)
        text = font.render(f'{self.healed_count}', True, (255, 255, 255))
        surf.blit(text, (surf.get_width() - img.get_width() - 30, 10))  # Dibuja el contador junto a la imagen
    

    async def run(self):
        # Reproducimos música de fondo
        pygame.mixer.music.load('data/music.wav')
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)
        
        # Loop infinito (-1: inf, 0: no, 1: 1, ...)
        self.sfx['ambience'].play(-1)
        
        while True:
            # Pantalla transparente
            self.display.fill((0, 0, 0, 0)) 

            # Dibujamos el fondo
            self.display_2.blit(self.assets['background'], (0, 0))
            
            self.screenshake = max(0, self.screenshake - 1)
            
            # Transición de niveles
            if not len(self.enemies):
                self.transition += 1
                if self.transition > 30:
                    self.level = min(self.level + 1, len(os.listdir('data/maps')) - 1)
                    self.load_level(self.level)
            if self.transition < 0:
                self.transition += 1
            
            # Estado de muerte
            if self.dead:
                self.dead += 1
                # Transición de reinicio
                if self.dead >= 10:
                    self.transition = min(30, self.transition + 1)
                # Despues de 40 frames reaparece
                if self.dead > 40:
                    self.load_level(self.level)
            
            # Desplazamiento de la camara | se divide entre 30 para un desplazamiento gradual
            self.scroll[0] += (self.player.rect().centerx - self.display.get_width() / 2 - self.scroll[0]) / 30
            self.scroll[1] += (self.player.rect().centery - self.display.get_height() / 2 - self.scroll[1]) / 30
            render_scroll = (int(self.scroll[0]), int(self.scroll[1]))
            
            # Generar partículas de hojas
            for rect in self.leaf_spawners:
                if random.random() * 49999 < rect.width * rect.height:
                    pos = (rect.x + random.random() * rect.width, rect.y + random.random() * rect.height)
                    self.particles.append(Particle(self, 'leaf', pos, velocity=[-0.1, 0.3], frame=random.randint(0, 20)))
            
            # Actualizamos y renderizamos las nubes en display_2 para que no tengan contorno
            self.clouds.update()
            self.clouds.render(self.display_2, offset=render_scroll)
            
            # Renderizamos el mapa | con contorno porque está en display
            self.tilemap.render(self.display, offset=render_scroll)

            # Actualizamos y renderizamos frutas
            for fruit in self.fruits.copy():
                fruit.update()
                fruit.render(self.display, offset=render_scroll)
            
            # Actualizamos y renderizamos los enemigos
            for enemy in self.enemies.copy():
                kill = enemy.update(self.tilemap, (0, 0))
                enemy.render(self.display, offset=render_scroll)
                if kill:
                    self.enemies.remove(enemy)
            
            # Actualizamos y renderizamos al jugador si no está muerto
            if not self.dead:
                self.player.update(self.tilemap, (self.movement[1] - self.movement[0], 0))
                self.player.render(self.display, offset=render_scroll)
            
            # Verificar si la vida del jugador es cero y marcar como muerto
            if self.player.health <= 0 and not self.dead:
                self.dead = 1
            
            # Actualizamos y renderizamos "chispas"
            for spark in self.sparks.copy():
                kill = spark.update()
                spark.render(self.display, offset=render_scroll)
                if kill:
                    self.sparks.remove(spark)

            # Renderizamos silueta de la pantalla para outline
            display_mask = pygame.mask.from_surface(self.display)
            display_sillhouette = display_mask.to_surface(setcolor=(0, 0, 0, 180), unsetcolor=(0, 0, 0, 0))
            for offset in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                self.display_2.blit(display_sillhouette, offset)
            
            # Actualizamos y renderizamos las partículas
            for particle in self.particles.copy():
                kill = particle.update()
                particle.render(self.display, offset=render_scroll)
                if particle.type == 'leaf':
                    particle.pos[0] += math.sin(particle.animation.frame * 0.035) * 0.3
                if kill:
                    self.particles.remove(particle)
            
            # Manejamos eventos de teclado y cierre ventana
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        self.movement[0] = True
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = True
                    if event.key == pygame.K_z or event.key == pygame.K_UP:
                        if self.player.jump():
                            self.sfx['jump'].play()
                    if event.key == pygame.K_x:
                        self.player.dash()
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_LEFT:
                        self.movement[0] = False
                    if event.key == pygame.K_RIGHT:
                        self.movement[1] = False

            # Renderizamos transición del nivel | círculo que se va abriendo 
            if self.transition:
                transition_surf = pygame.Surface(self.display.get_size())
                pygame.draw.circle(transition_surf, (255, 255, 255), (self.display.get_width() // 2, self.display.get_height() // 2), (30 - abs(self.transition)) * 8)
                transition_surf.set_colorkey((255, 255, 255))
                self.display.blit(transition_surf, (0, 0))
                
            self.display_2.blit(self.display, (0, 0))
            screenshake_offset = (random.random() * self.screenshake - self.screenshake / 2, random.random() * self.screenshake - self.screenshake / 2)

            # Escalamos display a screen
            self.screen.blit(pygame.transform.scale(self.display_2, self.screen.get_size()), screenshake_offset)

            # Dibujamos la barra de vida del jugador
            self.draw_health_bar(self.screen, 10, 10, self.player.health)

            # Dibujamos el contador de personas curadas
            self.draw_healed_counter(self.screen)

            pygame.display.update()
            self.clock.tick(60)

            await asyncio.sleep(0)


asyncio.run(Game().run())
