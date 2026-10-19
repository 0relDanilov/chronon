from pydantic import BaseModel, Field, JsonValue
from pydantic_extra_types.pendulum_dt import DateTime


class DatasetBase(BaseModel):
    type: str = Field(
        description="type of dataset (e.g. quam), useful for filtering data",
        max_length=60,
    )
    comment: str = Field(
        description="human-readable annotation of this dataset", max_length=300
    )
    parent_id: int | None = Field(
        description="optional id of parent dataset for same backend. This allows hierarchical organization of data"
    )
    data: JsonValue = Field(description="data as any valid JSON")


class DatasetInsert(DatasetBase):
    backend: str = Field(
        description="name of backend to which this dataset corresponds to",
        max_length=60,
    )
    producer: str = Field(description="author of the dataset", max_length=60)


class Dataset(DatasetInsert):
    id: int
    timestamp: DateTime = Field(
        description="automatically generated timestamp when the data was saved in database"
    )


class DatasetMeta(BaseModel):
    id: int
    timestamp: DateTime = Field(
        description="automatically generated timestamp when the data was saved in database"
    )
    type: str = Field(
        description="type of dataset (e.g. quam), useful for filtering data",
        max_length=60,
    )
    comment: str = Field(
        description="human-readable annotation of this dataset", max_length=300
    )
    producer: str = Field(description="author of the dataset", max_length=60)
    parent_id: int | None = Field(
        description="optional id of parent dataset for same backend. This allows hierarchical organization of data"
    )


class TimeSeries(BaseModel):
    id: int
    t: DateTime
    value: JsonValue
