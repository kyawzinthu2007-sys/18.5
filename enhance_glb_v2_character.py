# TSO AI character v2 — deduplication + rig + animation pipeline (Aug 2026).
#
# Source: a Blender export containing 8 identical copies of one character
# arranged in a grid (~56MB, 4096x4096 textures x3, no skeleton/animations).
# This script documents (does not re-run automatically — the source grid
# file is not committed) the steps used to turn that export into the
# shipped tso-ai-robot.glb:
#
# 1. DEDUPLICATE: isolate one instance from the 8-copy grid using spatial
#    gap detection (histogram of vertex positions along the grid axes to
#    find the empty bins between copies), then keep only triangles whose
#    3 vertices all fall inside that instance's bounds (avoids stray
#    cross-instance triangles at the boundary).
#
# 2. COMPRESS TEXTURES: the 3 PBR textures (base color, normal, metallic-
#    roughness) were exported at 4096x4096, which is far beyond what a
#    mascot rendered at a few hundred px on screen needs. Downscaled to
#    1024x1024 with Lanczos resampling — roughly a 12x size reduction
#    with no visible quality loss at the model's actual display size.
#
# 3. RIG (head/body split, NOT skeletal skinning): the source is a single
#    fused mesh with ~470 disconnected sub-shells (every fold, button, and
#    surface detail is its own tiny mesh island), so per-bone vertex
#    skinning was not attempted — there's no clean, non-destructive way to
#    weight-paint a mesh like that without a real DCC tool. Instead the
#    mesh was split into exactly two rigid pieces at the neck (found via a
#    radial-extent profile along the up axis — the waist point where the
#    silhouette narrows between head and shoulders), each becoming its own
#    glTF node: a Body root node and a Head child node offset to pivot at
#    the neck. This matches the animation TECHNIQUE already used by the
#    original tso-ai-robot.glb (plain node TRS animation, no skin/morph
#    targets), just with 2 rigid parts instead of that model's ~80.
#
# 4. ANIMATE: 6 clips (Idle, Wave, Talk, Happy, Smile, Wink) built as
#    keyframed translation/rotation/scale on the Body and Head nodes only.
#    IMPORTANT LIMITATION: the source sculpt has no separable arm, hand,
#    eyelid, or jaw geometry — the arm is fused solid with the sleeve with
#    no seam anywhere along its length (verified visually before deciding
#    this, see conversation notes). So unlike a fully rigged character,
#    none of these clips move a hand or face feature directly:
#      - Wave  -> whole-body lean/bow/rock greeting motion
#      - Talk  -> small rhythmic head bob + subtle body scale pulse
#      - Happy -> upward body bounce + head tilt-up
#      - Smile -> single gentle head tilt-and-settle
#      - Wink  -> quick playful head snap-tilt + tiny hop
#    All 6 names match exactly what index.html's TSOAvatar3D component
#    already calls, so no frontend animation-triggering logic needed to
#    change — only the comments explaining what the model can/can't do.
#
# If a future update adds a properly rigged/skinned source model (separate
# arm, eyelids, jaw), the frontend does not need to change at all — it
# already just asks for these 6 clip names by string and does not care
# how the motion is implemented under the hood.
