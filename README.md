# 🏰 UO3D Community Buildings Hub (3D Modelers & Artists)

> **The community modeling hub for recreating all 5,701 structures of Ultima Online in 3D.**  
> *Pick a building, refine it in Blender, and help bring Britannia to life!*

---

* [English](#-english)
  * [1. Contributor Quick Start](#1-contributor-quick-start)
  * [2. Downloading Only 1 Building (No 6GB Clone Required!)](#2-downloading-only-1-building-no-6gb-clone-required)
  * [3. What You Get in Every Building Folder](#3-what-you-get-in-every-building-folder)
  * [4. Blender Rules & Modeling Standards](#4-blender-rules--modeling-standards)
  * [5. How to Test Your Model in the Game](#5-how-to-test-your-model-in-the-game)
  * [6. Pull Request Submission Workflow](#6-pull-request-submission-workflow)
* [Português](#-português)
  * [1. Guia Rápido do Colaborador](#1-guia-rápido-do-colaborador)
  * [2. Baixando Apenas 1 Prédio (Sem Precisar Clonar 6GB!)](#2-baixando-apenas-1-prédio-sem-precisar-clonar-6gb)
  * [3. O que Vem na Pasta de Cada Construção](#3-o-que-vem-na-pasta-de-cada-construção)
  * [4. Regras do Blender e Padrões de Modelagem](#4-regras-do-blender-e-padrões-de-modelagem)
  * [5. Como Testar o seu Modelo no Jogo](#5-como-testar-o-seu-modelo-no-jogo)
  * [6. Como Enviar o seu Trabalho (Pull Requests)](#6-como-enviar-o-seu-trabalho-pull-requests)

---

# 🇬🇧 English

## 1. Contributor Quick Start

The goal of this repository is simple: **remodel the classic buildings of Ultima Online into beautiful, authentic 3D assets**.

We used an Advanced AI agent to construct the mathematical foundation for every building in the game:
- Extracted exact scales, heights, and coordinates from original UO game files.
- Built a 3D blockout mesh (`model_base.glb`) with door frames, wall thicknesses, and pitched roofs.
- Extracted all 2D textures/sprites into PNGs and rendered isometric reference screenshots.

**You never start from scratch.** You open the base model in Blender, use it as a 3D wireframe guide, and sculpt/remodel it into a finished game-ready asset.

---

## 2. Downloading Only 1 Building (No 6GB Clone Required!)

You **do NOT** need to clone the entire 6 GB repository if you only want to work on one building!

### Option A: Via GitHub Web Interface
1. Browse to your chosen town (e.g., `map0_felucca/britain/building_017_the_hammer_and_anvil_blacksmith/`).
2. Download the folder files directly or use [DownGit](https://downgit.github.io/) / GitHub folder downloaders.

### Option B: Git Sparse Checkout (Clone Only 1 Town)
```bash
git clone --filter=blob:none --sparse https://github.com/YOUR_USER/uo3d-community-buildings.git
cd uo3d-community-buildings
git sparse-checkout set map0_felucca/britain
```

### Option C: Python Helper
```bash
python tools/download_building.py britain/blacksmith
```

---

## 3. What You Get in Every Building Folder

Every single building folder contains:
- **`model_base.glb` & `model_base.obj`**: 3D blockout mesh **pre-centered at $(0, 0, 0)$** with scale $1 \text{ tile} = 1.0 \text{ meter}$.
- **`reference_2d.png`**: Original 2.5D game screenshot with a golden UOMAP coordinates banner.
- **`reference_2d_interior.png`**: Cutaway 2D render **without the roof**, showing the internal floor plan, furniture, counters, forges, and partition walls.
- **`info.json`**: World coordinates, dimensions, bounds, and UOMAP `Ctrl+G` teleport string.
- **`textures_2d/`**: Original UO sprites as transparent PNGs.

---

## 4. Blender Rules & Modeling Standards

### Rule 1: Scale & Pivot
- **1 Tile = Exactly 1.0 Meter**: In Blender, ensure Units are set to **Metric** (Scale = `1.0`).
- **Pivot at Origin $(0, 0, 0)$**: Keep the ground-floor center at $(0, 0, 0)$ matching `model_base.glb`. **Do not translate the model away from origin.**

### Rule 2: Alignment & Dimensions
- Use `model_base.glb` as your reference. Wall perimeters, door openings, and roof ridges should align with the base mesh so the building sits seamlessly on the game terrain.

### Rule 3: Textures & Materials
- Use standard PBR materials (`Albedo`, `Roughness`, `Normal`, and optional `Ambient Occlusion`).
- Textures should be $1024 \times 1024$ or $2048 \times 2048$ PNG/JPG.
- Export your final model as **`model_refined.glb`** (glTF 2.0 binary).

### Rule 4: Interiors
- If the building has an interior shown in `reference_2d_interior.png`, model the interior rooms and floors. Modular furniture and props (chests, counters, anvils) can be included.

---

## 5. How to Test Your Model in the Game

Once you save your finished model as `model_refined.glb` in your building's folder, test it in the Godot engine client (`uo3d-game`) with one command:
```bash
python tools/update_world_building.py <path_to_building_folder>
```
Open the Godot project and press **F5** — your new building will immediately load in the live game world at the exact coordinates with collision and shadows!

---

## 6. Pull Request Submission Workflow

1. Open an issue on GitHub to claim your building:  
   `[Claim] Map 0 - Britain - building_017_blacksmith`
2. Save your refined model inside the building folder:
   ```text
   map0_felucca/britain/building_017_the_hammer_and_anvil_blacksmith/
   ├── model_refined.glb     # Your finished 3D model
   ├── textures/             # PBR texture maps (if not embedded in GLB)
   └── screenshots/          # 2 or 3 beauty renders showing your work
   ```
3. Submit a Pull Request: `feat(britain): refine The Hammer & Anvil Blacksmith (building_017)`.

---
---

# 🇧🇷 Português

## 1. Guia Rápido do Colaborador

O objetivo deste repositório é simples e inspirador: **remodelar as construções clássicas do Ultima Online em modelos 3D modernos e autênticos**.

Utilizamos Inteligência Artificial Agêntica Avançada para estruturar toda a base matemática de cada construção:
- Escalas, alturas e coordenadas extraídas diretamente dos arquivos originais do UO.
- Modelo 3D volumétrico de referência (`model_base.glb`) com portas, espessura de paredes e caimento de telhados.
- Todas as texturas originais em PNG e fotos comparativas em 2D.

**Você nunca começa do zero.** Você abre o modelo base no Blender, utiliza-o como gabarito dimensional e foca na arte da modelagem e texturização.

---

## 2. Baixando Apenas 1 Prédio (Sem Precisar Clonar 6GB!)

Você **NÃO precisa** clonar todo o repositório de 6 GB se quiser trabalhar apenas em um prédio!

### Opção A: Pela Interface Web do GitHub
1. Navegue até a pasta da cidade escolhida (ex: `map0_felucca/britain/building_017_the_hammer_and_anvil_blacksmith/`).
2. Baixe os arquivos diretamente pelo navegador ou use ferramentas como [DownGit](https://downgit.github.io/).

### Opção B: Git Sparse Checkout (Clona Apenas 1 Cidade)
```bash
git clone --filter=blob:none --sparse https://github.com/SEU_USUARIO/uo3d-community-buildings.git
cd uo3d-community-buildings
git sparse-checkout set map0_felucca/britain
```

### Opção C: Script Auxiliar em Python
```bash
python tools/download_building.py britain/blacksmith
```

---

## 3. O que Vem na Pasta de Cada Construção

Cada pasta individual contém:
- **`model_base.glb` e `model_base.obj`**: Malha 3D base **centralizada na origem $(0, 0, 0)$** com proporção de 1 tile = 1 metro.
- **`reference_2d.png`**: Foto 2.5D do jogo original com barra de coordenadas para o **UOMAP**.
- **`reference_2d_interior.png`**: Foto em corte **sem telhado**, exibindo a planta baixa com móveis, balcões, forjas e divisórias.
- **`info.json`**: Metadados com dimensões em metros, contagem de polígonos e comando `Ctrl+G` para o UOMAP.
- **`textures_2d/`**: Todos os sprites originais em PNG transparente.

---

## 4. Regras do Blender e Padrões de Modelagem

### Regra 1: Escala e Pivô
- **1 Tile = Exatamente 1,0 Metro**: No Blender, configure as unidades da cena para **Métrico** (Scale = `1.0`).
- **Pivô Centralizado na Origem $(0, 0, 0)$**: Mantenha o centro da base do chão em $(0, 0, 0)$, idêntico ao `model_base.glb`. **Nunca mova o prédio para longe da origem.**

### Regra 2: Alinhamento e Dimensões
- Utilize `model_base.glb` como gabarito. Paredes externas, entradas de portas e cumeeiras de telhado devem coincidir com o modelo base para encaixar perfeitamente no mapa da engine.

### Regra 3: Texturas e Materiais
- Utilize materiais PBR padrão (`Albedo`, `Roughness`, `Normal` e opcionalmente `Ambient Occlusion`).
- Resoluções recomendadas: $1024 \times 1024$ ou $2048 \times 2048$.
- Salve o modelo finalizado como **`model_refined.glb`** (glTF 2.0 binário).

### Regra 4: Interiores
- Caso o prédio tenha interior exibido em `reference_2d_interior.png`, modele o chão e as divisórias internas. Móveis principais (balcões, forjas, mesas) podem ser incluídos.

---

## 5. Como Testar o seu Modelo no Jogo

Após salvar seu modelo finalizado como `model_refined.glb` na pasta do prédio, sincronize-o com o cliente Godot (`uo3d-game`) em um único comando:
```bash
python tools/update_world_building.py <caminho_da_pasta_do_predio>
```
Abra o projeto na Godot e aperte **F5** — seu novo modelo aparecerá imediatamente no jogo na posição exata, com colisão física e sombras!

---

## 6. Como Enviar o seu Trabalho (Pull Requests)

1. Abra uma issue no GitHub para registrar a escolha do prédio:  
   `[Claim] Map 0 - Britain - building_017_blacksmith`
2. Salve seu modelo refinado dentro da respectiva pasta:
   ```text
   map0_felucca/britain/building_017_the_hammer_and_anvil_blacksmith/
   ├── model_refined.glb     # Seu modelo 3D finalizado
   ├── textures/             # Texturas PBR (se não embutidas no GLB)
   └── screenshots/          # 2 ou 3 fotos mostrando o resultado
   ```
3. Abra um Pull Request: `feat(britain): refine The Hammer & Anvil Blacksmith (building_017)`.
