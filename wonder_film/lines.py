"""Ink-line extraction from 2x supersampled depth / normal / object-id passes.

Silhouettes come from discontinuities of inverse depth (planar surfaces are
linear in 1/z in screen space, so only real jumps survive), creases from the
angle between neighbouring normals, and contacts from object-id changes.
Lines are drawn heavier near the camera, thinner and lighter far away, then
area-downsampled to the output resolution for clean anti-aliasing.
"""
import cv2
import numpy as np

WATER, TERRAIN, MASONRY, TIMBER, CRANE, WORKER, SHIP, CITY, PROPS, STATUE, FIRE, TORCH = range(1, 13)


def _nearer(Z, a, b):
    return Z[a] <= Z[b]


def line_mask(Z, N, ID, thr_depth=0.22, thr_normal=0.24, thr_normal_terrain=0.55):
    H, W = Z.shape
    ID = np.rint(ID).astype(np.int32)
    bg = ~np.isfinite(Z) | (Z > 1e8)
    Zc = np.where(bg, 1e7, Z).astype(np.float32)
    inv = (1.0 / Zc).astype(np.float32)
    k = np.array([[1, 1, 1], [1, -8, 1], [1, 1, 1]], np.float32)
    lap = cv2.filter2D(inv, -1, k, borderType=cv2.BORDER_REPLICATE)
    rel = -lap / inv
    water = ID == WATER
    fire = (ID == FIRE) | (ID == TORCH)
    sil = (rel > thr_depth) & ~bg & ~water & ~fire

    # object-id contacts: mark the nearer pixel of each differing pair
    idl = np.zeros((H, W), bool)
    d = ID[:, 1:] != ID[:, :-1]
    near_left = Zc[:, :-1] <= Zc[:, 1:]
    idl[:, :-1] |= d & near_left
    idl[:, 1:] |= d & ~near_left
    d = ID[1:, :] != ID[:-1, :]
    near_top = Zc[:-1, :] <= Zc[1:, :]
    idl[:-1, :] |= d & near_top
    idl[1:, :] |= d & ~near_top
    idl &= ~bg & ~fire
    # water/terrain contact only where the terrain is the nearer surface (shoreline ink)
    sil |= idl

    # creases from normals
    Nn = N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    cr = np.zeros((H, W), np.float32)
    dx = 1.0 - np.sum(Nn[:, 1:] * Nn[:, :-1], -1)
    dy = 1.0 - np.sum(Nn[1:, :] * Nn[:-1, :], -1)
    cr[:, :-1] = np.maximum(cr[:, :-1], dx)
    cr[:-1, :] = np.maximum(cr[:-1, :], dy)
    thr = np.where(ID == TERRAIN, thr_normal_terrain, thr_normal)
    crease = (cr > thr) & ~bg & ~water & ~fire & ~sil

    # thickness by distance; thin members (timber, ropes, figures) stay fine-lined
    light = np.isin(ID, (TIMBER, CRANE, WORKER, CITY))
    near = (Zc < 170) & ~light
    mid = (Zc >= 170) & (Zc < 520) & ~light
    silf = sil.astype(np.uint8)
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    k2 = np.ones((2, 2), np.uint8)
    sil_near = cv2.dilate(silf * near, k3)
    sil_mid = cv2.dilate(silf * mid, k2)
    sil_far = silf * (~near & ~mid)
    crf = (crease & ~light).astype(np.uint8)
    cr_near = cv2.dilate(crf * near, k2)
    cr_rest = crf * (~near)
    ink = np.maximum.reduce([sil_near, sil_mid, sil_far]).astype(np.float32)
    ink = np.maximum(ink, 0.8 * np.maximum(cr_near, cr_rest).astype(np.float32))
    weight = np.where(light, 0.5, 1.0).astype(np.float32)
    ink *= weight
    # fade with distance (a pen gets lighter towards the horizon)
    zmin = cv2.erode(Zc, k3)
    fade = np.clip(1.25 - zmin / 1100.0, 0.18, 1.0)
    ink *= fade
    return ink


def save_lines(path, Z, N, ID, out_size):
    ink = line_mask(Z, N, ID)
    small = cv2.resize(ink, tuple(out_size), interpolation=cv2.INTER_AREA)
    small = np.clip(small * 1.2, 0, 1)
    cv2.imwrite(path, (small * 255 + 0.5).astype(np.uint8))
