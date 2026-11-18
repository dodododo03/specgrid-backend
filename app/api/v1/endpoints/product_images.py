from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints.products import ProductId
from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError
from app.core.storage import Storage, get_storage
from app.schemas.product import ImageOrderUpdate, ProductDetail
from app.services import image_service

router = APIRouter(prefix="/products/{product_id}/images", tags=["product images"])

StorageDep = Annotated[Storage, Depends(get_storage)]


async def read_limited(upload: UploadFile) -> bytes:
    limit = settings.max_image_upload_mb * 1024 * 1024
    data = await upload.read(limit + 1)  # read one byte past the limit instead of the whole file
    if len(data) > limit:
        raise PayloadTooLargeError(f"이미지는 한 장당 {settings.max_image_upload_mb}MB 이하만 업로드할 수 있습니다.")
    return data


@router.post(
    "",
    response_model=ProductDetail,
    status_code=201,
    summary="상품 사진 업로드 (여러 장)",
    description=(
        "JPG/PNG/WebP, 장당 10MB, 상품당 최대 10장. 사진은 WebP로 재인코딩되며 "
        "위치정보(EXIF)는 제거됩니다. 한 장이라도 잘못되면 전체가 저장되지 않습니다."
    ),
)
async def upload_images(
    product_id: ProductId,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    files: Annotated[list[UploadFile], File(description="이미지 파일 (여러 개 선택 가능)")],
):
    if len(files) > settings.max_images_per_product:
        raise PayloadTooLargeError(f"한 번에 최대 {settings.max_images_per_product}장까지 올릴 수 있습니다.")
    uploads = [await read_limited(f) for f in files]
    # Decoding/re-encoding is CPU-bound and the DB session is sync: run in a worker thread.
    return await run_in_threadpool(image_service.add_images, db, storage, product_id, user, uploads)


@router.delete("/{image_id}", response_model=ProductDetail, summary="상품 사진 삭제")
def delete_image(product_id: ProductId, image_id: ProductId, user: CurrentUser, db: DbSession, storage: StorageDep):
    return image_service.delete_image(db, storage, product_id, image_id, user)


@router.put("/order", response_model=ProductDetail, summary="상품 사진 순서 변경 (첫 번째가 대표 사진)")
def reorder_images(product_id: ProductId, data: ImageOrderUpdate, user: CurrentUser, db: DbSession):
    return image_service.reorder_images(db, product_id, user, data.image_ids)
