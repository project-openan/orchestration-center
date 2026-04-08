import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import pickle
from loguru import logger


class SolutionPackageManager:
    """管理solutionpackage的存储和检索功能"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        初始化SolutionPackageManager
        
        Args:
            storage_dir: 存储目录路径，默认为与framework同级的data/solution_packages
        """
        if storage_dir is None:
            # 获取当前文件的绝对路径，然后找到项目根目录（framework的父级）
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent  # framework目录
            self.storage_dir = project_root / "data" / "solution_packages"
        else:
            self.storage_dir = Path(storage_dir)
        
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"SolutionPackageManager initialized with storage directory: {self.storage_dir}")
    
    def _get_storage_path(self, pdf_filename: str) -> Path:
        """
        根据PDF文件名获取存储路径
        
        Args:
            pdf_filename: PDF文件名
            
        Returns:
            Path: 存储文件路径
        """
        # 移除文件扩展名，使用纯文件名作为存储文件名
        filename_without_ext = Path(pdf_filename).stem
        storage_filename = f"{filename_without_ext}.json"
        return self.storage_dir / storage_filename
    
    def store_solution_package(self, pdf_filename: str, chapters_dict: Dict[str, str]) -> bool:
        """
        存储solutionpackage数据
        
        Args:
            pdf_filename: PDF文件名
            chapters_dict: 通过extract_all_chapters方法提取的章节字典
            
        Returns:
            bool: 存储是否成功
        """
        try:
            storage_path = self._get_storage_path(pdf_filename)
            
            # 准备存储数据
            storage_data = {
                "pdf_filename": pdf_filename,
                "chapters": chapters_dict,
                "chapter_count": len(chapters_dict),
                "chapter_titles": list(chapters_dict.keys())
            }
            
            # 写入JSON文件
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Successfully stored solution package for '{pdf_filename}' at {storage_path}")
            logger.info(f"Stored {len(chapters_dict)} chapters")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store solution package for '{pdf_filename}': {e}")
            return False
    
    def retrieve_by_filename(self, pdf_filename: str) -> Optional[Dict[str, Any]]:
        """
        按PDF文件名检索solutionpackage数据
        
        Args:
            pdf_filename: PDF文件名
            
        Returns:
            Optional[Dict[str, Any]]: 检索到的数据，包含章节字典等信息
        """
        try:
            storage_path = self._get_storage_path(pdf_filename)
            
            if not storage_path.exists():
                logger.warning(f"No solution package found for '{pdf_filename}' at {storage_path}")
                return None
            
            # 读取JSON文件
            with open(storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Successfully retrieved solution package for '{pdf_filename}'")
            logger.info(f"Retrieved {data.get('chapter_count', 0)} chapters")
            return data
            
        except Exception as e:
            logger.error(f"Failed to retrieve solution package for '{pdf_filename}': {e}")
            return None
    
    def retrieve_all(self) -> List[Dict[str, Any]]:
        """
        全量检索所有存储的solutionpackage数据
        
        Returns:
            List[Dict[str, Any]]: 所有存储的solutionpackage数据列表
        """
        try:
            all_packages = []
            
            # 遍历存储目录中的所有JSON文件
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        all_packages.append(data)
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(all_packages)} solution packages in total")
            return all_packages
            
        except Exception as e:
            logger.error(f"Failed to retrieve all solution packages: {e}")
            return []
    
    def get_all_filenames(self) -> List[str]:
        """
        获取所有已存储的PDF文件名列表
        
        Returns:
            List[str]: PDF文件名列表
        """
        try:
            filenames = []
            
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "pdf_filename" in data:
                            filenames.append(data["pdf_filename"])
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    continue
            
            return filenames
            
        except Exception as e:
            logger.error(f"Failed to get all filenames: {e}")
            return []
    
    def delete_by_filename(self, pdf_filename: str) -> bool:
        """
        删除指定PDF文件名的solutionpackage数据
        
        Args:
            pdf_filename: PDF文件名
            
        Returns:
            bool: 删除是否成功
        """
        try:
            storage_path = self._get_storage_path(pdf_filename)
            
            if not storage_path.exists():
                logger.warning(f"No solution package found for '{pdf_filename}' to delete")
                return False
            
            storage_path.unlink()
            logger.info(f"Successfully deleted solution package for '{pdf_filename}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete solution package for '{pdf_filename}': {e}")
            return False
    
    def get_chapter_content(self, pdf_filename: str, chapter_title: str) -> Optional[str]:
        """
        获取指定PDF文件中特定章节的内容
        
        Args:
            pdf_filename: PDF文件名
            chapter_title: 章节标题
            
        Returns:
            Optional[str]: 章节内容，如果不存在则返回None
        """
        try:
            data = self.retrieve_by_filename(pdf_filename)
            if not data or "chapters" not in data:
                return None
            
            chapters = data["chapters"]
            return chapters.get(chapter_title)
            
        except Exception as e:
            logger.error(f"Failed to get chapter content for '{chapter_title}' in '{pdf_filename}': {e}")
            return None
    
    def search_chapters_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        在所有存储的solutionpackage中搜索包含关键词的章节
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            List[Dict[str, Any]]: 包含匹配结果的列表，每个结果包含PDF文件名和匹配的章节
        """
        try:
            all_packages = self.retrieve_all()
            results = []
            
            for package in all_packages:
                pdf_filename = package.get("pdf_filename", "")
                chapters = package.get("chapters", {})
                
                matching_chapters = {}
                for chapter_title, chapter_content in chapters.items():
                    if keyword.lower() in chapter_content.lower():
                        matching_chapters[chapter_title] = chapter_content
                
                if matching_chapters:
                    results.append({
                        "pdf_filename": pdf_filename,
                        "matching_chapters": matching_chapters,
                        "match_count": len(matching_chapters)
                    })
            
            logger.info(f"Found {len(results)} packages with chapters containing keyword '{keyword}'")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search chapters by keyword '{keyword}': {e}")
            return []
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            Dict[str, Any]: 存储统计信息
        """
        try:
            all_packages = self.retrieve_all()
            total_packages = len(all_packages)
            total_chapters = sum(package.get("chapter_count", 0) for package in all_packages)
            
            return {
                "storage_directory": str(self.storage_dir),
                "total_packages": total_packages,
                "total_chapters": total_chapters,
                "package_filenames": [p.get("pdf_filename", "") for p in all_packages]
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {
                "storage_directory": str(self.storage_dir),
                "total_packages": 0,
                "total_chapters": 0,
                "package_filenames": []
            }