// Shrink phone photos in the browser before uploading.
//
// Phone cameras produce files the server refuses or that are slow on mobile data:
// 50–200 MP shots (over the server's pixel limit), 10 MB+ files, and HEIC on iPhones.
// Decoding in the browser and re-encoding to a ≤2048px JPEG fixes all three; the server
// still validates and re-encodes everything, so this is a convenience, not a trust boundary.

const MAX_SIDE = 2048;
const KEEP_AS_IS_BYTES = 3 * 1024 * 1024; // small JPG/PNG/WebP within MAX_SIDE go up untouched
const SERVER_MAX_BYTES = 10 * 1024 * 1024;
const SERVER_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const PHOTO_ACCEPT = "image/*";

async function decode(file) {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
      /* fall through to <img>, which some browsers decode more formats with */
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function jpegName(name) {
  return (name || "photo").replace(/\.[^.]+$/, "") + ".jpg";
}

/**
 * Returns a File ready to upload, or throws Error with a message for the user.
 */
export async function preparePhoto(file) {
  if (file.type && !file.type.startsWith("image/")) throw new Error(`${file.name}: 사진 파일만 올릴 수 있어요.`);
  let image;
  try {
    image = await decode(file);
  } catch {
    // Can't decode here (e.g. HEIC on Android/Chrome): send it only if the server can take it as is.
    if (SERVER_TYPES.includes(file.type) && file.size <= SERVER_MAX_BYTES) return file;
    if (/hei[cf]/i.test(file.type) || /\.hei[cf]$/i.test(file.name)) {
      throw new Error(`${file.name}: HEIC 사진은 이 브라우저에서 열 수 없어요. JPG로 저장한 사진을 올려 주세요.`);
    }
    throw new Error(`${file.name}: 사진을 읽을 수 없어요.`);
  }
  const width = image.width || image.naturalWidth;
  const height = image.height || image.naturalHeight;
  if (SERVER_TYPES.includes(file.type) && file.size <= KEEP_AS_IS_BYTES && Math.max(width, height) <= MAX_SIDE) {
    image.close?.();
    return file; // keeps PNG transparency and avoids a needless re-encode
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; // JPEG has no transparency
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  image.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
  if (!blob) throw new Error(`${file.name}: 사진을 변환하지 못했어요.`);
  return new File([blob], jpegName(file.name), { type: "image/jpeg" });
}
