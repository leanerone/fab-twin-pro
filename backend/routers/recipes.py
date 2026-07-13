"""配方API路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Recipe

router = APIRouter()


@router.get("/")
def get_recipes(machine_id: str = None, db: Session = Depends(get_db)):
    """获取配方列表"""
    query = db.query(Recipe)
    if machine_id:
        query = query.filter(Recipe.machine_id == machine_id)
    recipes = query.all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "machine_id": r.machine_id,
            "process_type": r.process_type,
            "temperature": r.temperature,
            "pressure": r.pressure,
            "rf_power": r.rf_power,
            "gas_flow": r.gas_flow,
            "process_time": r.process_time,
        }
        for r in recipes
    ]


@router.get("/{recipe_id}")
def get_recipe(recipe_id: str, db: Session = Depends(get_db)):
    """获取单个配方详情"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        return {"error": "Recipe not found"}
    return {
        "id": recipe.id,
        "name": recipe.name,
        "machine_id": recipe.machine_id,
        "process_type": recipe.process_type,
        "temperature": recipe.temperature,
        "pressure": recipe.pressure,
        "rf_power": recipe.rf_power,
        "gas_flow": recipe.gas_flow,
        "process_time": recipe.process_time,
        "updated_at": recipe.updated_at,
    }
